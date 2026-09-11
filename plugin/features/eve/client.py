from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
from dataclasses import dataclass
from datetime import date
from email.utils import parsedate_to_datetime
from typing import Protocol

import requests

logger = logging.getLogger(__name__)

JITA_REGION_ID = 10000002
JITA_STATION_ID = 60003760
PLEX_REGION_ID = 19000001
PLEX_TYPE_ID = 44992


@dataclass(frozen=True)
class MarketQuote:
    type_id: int
    market: str
    sell_min: float | None
    buy_max: float | None


@dataclass(frozen=True)
class MarketHistoryDay:
    date: date
    average: float
    highest: float
    lowest: float
    volume: int
    source: str = "CCP ESI regional history"


@dataclass
class _CacheEntry:
    data: list[dict]
    expires_at: float
    etag: str | None
    last_modified: str | None
    pages: int


class OrderPageCache(Protocol):
    def get(self, key: str) -> _CacheEntry | None: ...

    def set(self, key: str, entry: _CacheEntry) -> None: ...


class MarketClient(Protocol):
    def quote(self, type_id: int, market: str = "jita") -> MarketQuote: ...

    def history(
        self, type_id: int, market: str = "jita", days: int = 30
    ) -> list[MarketHistoryDay]: ...


class MemoryOrderCache:
    def __init__(self):
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> _CacheEntry | None:
        with self._lock:
            return self._cache.get(key)

    def set(self, key: str, entry: _CacheEntry) -> None:
        with self._lock:
            self._cache[key] = entry


class RedisOrderCache:
    """Redis 异常只影响共享缓存，自动降级到进程内缓存。"""

    def __init__(self, url: str, prefix: str = "yuxuandnf:eve", stale_seconds: int = 3600):
        import redis

        self._redis = redis.Redis.from_url(url, decode_responses=True)
        self._prefix = prefix.rstrip(":")
        self._stale_seconds = max(300, stale_seconds)
        self._memory = MemoryOrderCache()

    def _key(self, key: str) -> str:
        # URL 本身已经包含 region、type 和 page；使用稳定哈希避免超长 Redis key。
        import hashlib

        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return f"{self._prefix}:orders:{digest}"

    def get(self, key: str) -> _CacheEntry | None:
        try:
            raw = self._redis.get(self._key(key))
            if raw:
                payload = json.loads(raw)
                entry = _CacheEntry(
                    data=payload["data"],
                    expires_at=float(payload["expires_at"]),
                    etag=payload.get("etag"),
                    last_modified=payload.get("last_modified"),
                    pages=int(payload.get("pages", 1)),
                )
                self._memory.set(key, entry)
                return entry
        except Exception as error:
            logger.warning("读取 EVE Redis 缓存失败，使用内存缓存: %s", error)
        return self._memory.get(key)

    def set(self, key: str, entry: _CacheEntry) -> None:
        self._memory.set(key, entry)
        payload = json.dumps(
            {
                "data": entry.data,
                "expires_at": entry.expires_at,
                "etag": entry.etag,
                "last_modified": entry.last_modified,
                "pages": entry.pages,
            },
            separators=(",", ":"),
        )
        try:
            self._redis.setex(self._key(key), self._stale_seconds, payload)
        except Exception as error:
            logger.warning("写入 EVE Redis 缓存失败，使用内存缓存: %s", error)


class EsiMarketClient:
    def __init__(
        self,
        timeout: int = 20,
        cache_seconds: int = 300,
        user_agent: str = "",
        cache: OrderPageCache | None = None,
    ):
        self.timeout = timeout
        self.cache_seconds = cache_seconds
        self.headers = {
            "User-Agent": user_agent,
            "X-Tenant": "tranquility",
            "X-Compatibility-Date": "2020-01-01",
        }
        self.cache = cache or MemoryOrderCache()

    def quote(self, type_id: int, market: str = "jita") -> MarketQuote:
        if market == "global":
            region_id, location_id, label = PLEX_REGION_ID, None, "Global PLEX Market"
        elif market == "jita":
            region_id, location_id, label = JITA_REGION_ID, JITA_STATION_ID, "吉他 4-4"
        else:
            raise ValueError(f"不支持的市场：{market}")
        base = f"https://esi.evetech.net/markets/{region_id}/orders"
        params = {"order_type": "all", "type_id": type_id, "page": 1}
        first, pages, modified = self._get_page(base, params)
        orders = list(first)
        for page in range(2, pages + 1):
            params["page"] = page
            data, _, page_modified = self._get_page(base, params)
            if modified and page_modified and page_modified != modified:
                raise RuntimeError("ESI 订单分页跨越了缓存刷新，请稍后重试")
            orders.extend(data)
        if location_id is not None:
            orders = [order for order in orders if int(order.get("location_id", 0)) == location_id]
        sells = [order for order in orders if not order.get("is_buy_order")]
        buys = [order for order in orders if order.get("is_buy_order")]
        return MarketQuote(
            type_id=type_id,
            market=label,
            sell_min=min((float(order["price"]) for order in sells), default=None),
            buy_max=max((float(order["price"]) for order in buys), default=None),
        )

    def history(self, type_id: int, market: str = "jita", days: int = 30) -> list[MarketHistoryDay]:
        if market == "global":
            region_id = PLEX_REGION_ID
        elif market == "jita":
            region_id = JITA_REGION_ID
        else:
            raise ValueError(f"不支持的市场：{market}")
        url = f"https://esi.evetech.net/markets/{region_id}/history/"
        data, _, _ = self._get_page(url, {"type_id": type_id})
        history = [
            MarketHistoryDay(
                date=date.fromisoformat(str(row["date"])),
                average=float(row["average"]),
                highest=float(row["highest"]),
                lowest=float(row["lowest"]),
                volume=int(row["volume"]),
            )
            for row in data
        ]
        history.sort(key=lambda row: row.date)
        return history[-max(1, days) :]

    def _get_page(self, url: str, params: dict) -> tuple[list[dict], int, str | None]:
        key = requests.Request("GET", url, params=params).prepare().url or url
        now = time.time()
        cached = self.cache.get(key)
        if cached and cached.expires_at > now:
            return cached.data, cached.pages, cached.last_modified
        headers = dict(self.headers)
        if cached and cached.etag:
            headers["If-None-Match"] = cached.etag
        if cached and cached.last_modified:
            headers["If-Modified-Since"] = cached.last_modified
        response = requests.get(url, params=params, headers=headers, timeout=self.timeout)
        if response.status_code == 304 and cached:
            cached.expires_at = now + self.cache_seconds
            cached.pages = int(response.headers.get("X-Pages", str(cached.pages)))
            self.cache.set(key, cached)
            return cached.data, cached.pages, cached.last_modified
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError("ESI 市场接口返回格式异常")
        expires_at = self._expires_at(response.headers.get("Expires"), now)
        pages = int(response.headers.get("X-Pages", "1"))
        entry = _CacheEntry(
            data=data,
            expires_at=expires_at,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            pages=pages,
        )
        self.cache.set(key, entry)
        return data, pages, entry.last_modified

    def _expires_at(self, expires: str | None, now: float) -> float:
        if expires:
            try:
                return max(now + 1, parsedate_to_datetime(expires).timestamp())
            except (TypeError, ValueError):
                pass
        return now + self.cache_seconds


class Adam4EveHistoryClient:
    """Read Jita 4-4 daily best bid/ask history published by Adam4EVE."""

    DEFAULT_URL = "https://www.adam4eve.eu/hub_type_history.php"
    SOURCE = "Adam4EVE Jita 4-4"
    _ROW = re.compile(
        r"\[\s*new Date\('(?P<date>\d{4}-\d{2}-\d{2})'\)\s*,"
        r"\s*(?P<buy_high>[-+\d.eE]+|NaN|null)\s*,"
        r"\s*(?:[-+\d.eE]+|NaN|null)\s*,"
        r"\s*(?:[-+\d.eE]+|NaN|null)\s*,"
        r"\s*(?:[-+\d.eE]+|NaN|null)\s*,"
        r"\s*(?P<sell_low>[-+\d.eE]+|NaN|null)\s*,"
        r"\s*(?:[-+\d.eE]+|NaN|null)\s*\]",
        re.IGNORECASE,
    )

    def __init__(
        self,
        timeout: int = 30,
        cache_seconds: int = 21600,
        user_agent: str = "",
        cache: OrderPageCache | None = None,
        url: str = DEFAULT_URL,
    ):
        self.timeout = timeout
        self.cache_seconds = max(300, cache_seconds)
        self.headers = {"User-Agent": user_agent}
        self.cache = cache or MemoryOrderCache()
        self.url = url

    def history(self, type_id: int, days: int = 30) -> list[MarketHistoryDay]:
        params = {"typeID": type_id, "stationID": JITA_STATION_ID, "mode": "min"}
        key = requests.Request("GET", self.url, params=params).prepare().url or self.url
        now = time.time()
        cached = self.cache.get(key)
        if cached and cached.expires_at > now:
            return self._decode(cached.data, days)

        response = requests.get(
            self.url,
            params=params,
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        rows = self._parse(response.text)
        if not rows:
            raise ValueError("Adam4EVE 未返回可用的吉他历史价格")
        self.cache.set(
            key,
            _CacheEntry(
                data=rows,
                expires_at=now + self.cache_seconds,
                etag=None,
                last_modified=response.headers.get("Last-Modified"),
                pages=1,
            ),
        )
        return self._decode(rows, days)

    @classmethod
    def _parse(cls, html: str) -> list[dict]:
        marker = 'new Dygraph(document.getElementById("div_prices")'
        start = html.find(marker)
        if start < 0:
            return []
        end = html.find("labels:", start)
        graph = html[start : end if end >= 0 else len(html)]
        rows: list[dict] = []
        for match in cls._ROW.finditer(graph):
            buy_high = cls._number(match.group("buy_high"))
            sell_low = cls._number(match.group("sell_low"))
            if buy_high is None and sell_low is None:
                continue
            # A missing side is plotted as a point instead of inventing a spread.
            buy_high = sell_low if buy_high is None else buy_high
            sell_low = buy_high if sell_low is None else sell_low
            rows.append(
                {
                    "date": match.group("date"),
                    "buy_high": buy_high,
                    "sell_low": sell_low,
                }
            )
        return rows

    @staticmethod
    def _number(value: str) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @classmethod
    def _decode(cls, rows: list[dict], days: int) -> list[MarketHistoryDay]:
        history = [
            MarketHistoryDay(
                date=date.fromisoformat(str(row["date"])),
                average=(float(row["buy_high"]) + float(row["sell_low"])) / 2,
                highest=float(row["sell_low"]),
                lowest=float(row["buy_high"]),
                volume=0,
                source=cls.SOURCE,
            )
            for row in rows
        ]
        history.sort(key=lambda row: row.date)
        return history[-max(1, days) :]


class EveMarketClient:
    """Market facade: ESI quotes, Adam4EVE station history, ESI fallback."""

    def __init__(
        self,
        esi: EsiMarketClient,
        station_history: Adam4EveHistoryClient | None = None,
        fallback_to_esi: bool = True,
    ):
        self.esi = esi
        self.station_history = station_history
        self.fallback_to_esi = fallback_to_esi

    def quote(self, type_id: int, market: str = "jita") -> MarketQuote:
        return self.esi.quote(type_id, market)

    def history(self, type_id: int, market: str = "jita", days: int = 30) -> list[MarketHistoryDay]:
        if market == "jita" and self.station_history is not None:
            try:
                return self.station_history.history(type_id, days)
            except Exception:
                if not self.fallback_to_esi:
                    raise
                logger.exception(
                    "Adam4EVE 吉他历史价格查询失败，降级到 ESI 区域历史: type_id=%s",
                    type_id,
                )
        return self.esi.history(type_id, market, days)
