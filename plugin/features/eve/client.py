from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
from dataclasses import dataclass
from datetime import date
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
    source: str = "market history"


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

        self._redis = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
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


class FuzzworkMarketClient:
    """Batch current prices using Fuzzwork station/region aggregates."""

    DEFAULT_URL = "https://market.fuzzwork.co.uk/aggregates/"
    supports_batch_quotes = True

    def __init__(
        self,
        timeout: int = 20,
        cache_seconds: int = 300,
        user_agent: str = "",
        cache: OrderPageCache | None = None,
        url: str = DEFAULT_URL,
    ):
        self.timeout = timeout
        self.cache_seconds = cache_seconds
        self.headers = {"User-Agent": user_agent}
        self.cache = cache or MemoryOrderCache()
        self.url = url

    def quote(self, type_id: int, market: str = "jita") -> MarketQuote:
        return self.quote_many([type_id], market)[type_id]

    def quote_many(self, type_ids: list[int], market: str = "jita") -> dict[int, MarketQuote]:
        if market == "jita":
            scope = {"station": JITA_STATION_ID}
            label = "吉他 4-4"
        elif market == "global":
            scope = {"region": PLEX_REGION_ID}
            label = "Global PLEX Market"
        else:
            raise ValueError(f"不支持的市场：{market}")
        ids = list(dict.fromkeys(int(type_id) for type_id in type_ids))
        if not ids:
            return {}
        params = {**scope, "types": ",".join(map(str, ids))}
        key = requests.Request("GET", self.url, params=params).prepare().url or self.url
        now = time.time()
        cached = self.cache.get(key)
        if cached and cached.expires_at > now:
            payload = cached.data[0] if cached.data else {}
        else:
            try:
                response = requests.get(
                    self.url,
                    params=params,
                    headers=self.headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("Fuzzwork 行情接口返回格式异常")
                self.cache.set(
                    key,
                    _CacheEntry(
                        data=[payload],
                        expires_at=now + self.cache_seconds,
                        etag=None,
                        last_modified=None,
                        pages=1,
                    ),
                )
            except (requests.RequestException, ValueError) as error:
                if not cached:
                    raise RuntimeError("吉他备用行情接口暂时不可用") from error
                logger.warning("Fuzzwork 请求失败，使用过期缓存 %s: %s", key, error)
                payload = cached.data[0] if cached.data else {}
        return {type_id: self._decode_quote(type_id, payload, label) for type_id in ids}

    @staticmethod
    def _decode_quote(type_id: int, payload: dict, label: str) -> MarketQuote:
        row = payload.get(str(type_id), {})
        buy = row.get("buy", {}) if isinstance(row, dict) else {}
        sell = row.get("sell", {}) if isinstance(row, dict) else {}
        return MarketQuote(
            type_id,
            label,
            FuzzworkMarketClient._price(sell.get("min")),
            FuzzworkMarketClient._price(buy.get("max")),
        )

    @staticmethod
    def _price(value: object) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) and number > 0 else None


class EveMarketClient:
    """Market facade with independent current-price and history providers."""

    supports_batch_quotes = True

    def __init__(
        self,
        current: MarketClient,
        station_history: Adam4EveHistoryClient | None = None,
        history_fallback: MarketClient | None = None,
        quote_fallback: MarketClient | None = None,
    ):
        self.current = current
        self.station_history = station_history
        self.history_fallback = history_fallback
        self.quote_fallback = quote_fallback

    def quote(self, type_id: int, market: str = "jita") -> MarketQuote:
        try:
            return self.current.quote(type_id, market)
        except Exception:
            if self.quote_fallback is None:
                raise
            logger.exception("主行情查询失败，使用备用行情: type_id=%s", type_id)
            return self.quote_fallback.quote(type_id, market)

    def quote_many(self, type_ids: list[int], market: str = "jita") -> dict[int, MarketQuote]:
        primary_many = (
            getattr(self.current, "quote_many", None)
            if getattr(self.current, "supports_batch_quotes", False) is True
            else None
        )
        if callable(primary_many):
            return primary_many(type_ids, market)
        fallback_many = (
            getattr(self.quote_fallback, "quote_many", None)
            if getattr(self.quote_fallback, "supports_batch_quotes", False) is True
            else None
        )
        if callable(fallback_many):
            return fallback_many(type_ids, market)
        return {type_id: self.quote(type_id, market) for type_id in type_ids}

    def history(self, type_id: int, market: str = "jita", days: int = 30) -> list[MarketHistoryDay]:
        if market == "jita" and self.station_history is not None:
            try:
                return self.station_history.history(type_id, days)
            except Exception:
                logger.exception("Adam4EVE 吉他历史价格查询失败: type_id=%s", type_id)
        if self.history_fallback is not None:
            return self.history_fallback.history(type_id, market, days)
        return []
