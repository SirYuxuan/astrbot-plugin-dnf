from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class KbReport:
    character_id: int
    character_name: str
    corporation_name: str | None
    alliance_name: str | None
    security_status: float | None
    danger_ratio: float
    gang_ratio: float
    ships_destroyed: int
    ships_lost: int
    isk_destroyed: float
    isk_lost: float
    solo_kills: int
    solo_losses: int
    entity_type: str = "character"

    @property
    def has_activity(self) -> bool:
        return bool(self.ships_destroyed or self.ships_lost or self.isk_destroyed or self.isk_lost)


class KbClient:
    ESI_IDS_URL = "https://esi.evetech.net/latest/universe/ids/"
    ESI_NAMES_URL = "https://esi.evetech.net/latest/universe/names/"
    ZKILL_STATS_URL = "https://zkillboard.com/api/stats/characterID/{character_id}/kills/"
    ZKILL_ENTITY_STATS_URL = "https://zkillboard.com/api/stats/{entity_type}/{entity_id}/kills/"
    ZKILL_RECENT_URL = "https://zkillboard.com/api/characterID/{character_id}/{activity}/"
    ESI_KILLMAIL_URL = "https://esi.evetech.net/latest/killmails/{killmail_id}/{killmail_hash}/"

    def __init__(
        self,
        *,
        timeout: int = 15,
        cache_seconds: int = 600,
        user_agent: str = "astrbot-plugin-dnf/1.7",
        esi_ids_url: str = ESI_IDS_URL,
        esi_names_url: str = ESI_NAMES_URL,
        zkill_stats_url: str = ZKILL_STATS_URL,
        zkill_entity_stats_url: str = ZKILL_ENTITY_STATS_URL,
        zkill_recent_url: str = ZKILL_RECENT_URL,
        esi_killmail_url: str = ESI_KILLMAIL_URL,
    ) -> None:
        self.timeout = max(1, timeout)
        self.cache_seconds = max(60, cache_seconds)
        self.headers = {
            "User-Agent": user_agent.strip() or "astrbot-plugin-dnf/1.7",
            "Accept-Encoding": "gzip",
        }
        self.esi_ids_url = esi_ids_url
        self.esi_names_url = esi_names_url
        self.zkill_stats_url = zkill_stats_url
        self.zkill_entity_stats_url = zkill_entity_stats_url
        self.zkill_recent_url = zkill_recent_url
        self.esi_killmail_url = esi_killmail_url
        self._cache: dict[str, tuple[float, KbReport | None]] = {}
        self._cache_lock = threading.Lock()

    def query(self, character_name: str) -> KbReport | None:
        return self.query_entity("character", character_name)

    def names(self, entity_ids: list[int]) -> dict[int, str]:
        return self._resolve_names(entity_ids)

    def latest_character_killmail(
        self, character_id: int, activity: str
    ) -> dict[str, Any] | None:
        try:
            character_id = int(character_id)
        except (TypeError, ValueError) as error:
            raise ValueError("EVE 角色 ID 无效") from error
        if character_id <= 0 or activity not in {"kills", "losses"}:
            raise ValueError("EVE 角色 ID 或 KB 类型无效")
        response = requests.get(
            self.zkill_recent_url.format(character_id=character_id, activity=activity),
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("zKillboard 最近记录格式无效")
        records = [
            row for row in payload
            if isinstance(row, dict) and self._positive_int(row.get("killmail_id"))
        ]
        if not records:
            return None
        summary = max(
            records,
            key=lambda row: (
                str(row.get("killmail_time", "")),
                self._integer(row.get("killmail_id")),
            ),
        )
        killmail_id = int(summary["killmail_id"])
        zkb = summary.get("zkb") if isinstance(summary.get("zkb"), dict) else {}
        esi = {
            key: summary[key]
            for key in ("attackers", "killmail_time", "solar_system_id", "victim")
            if key in summary
        }
        killmail_hash = str(zkb.get("hash", "")).strip()
        if killmail_hash:
            try:
                detail_response = requests.get(
                    self.esi_killmail_url.format(
                        killmail_id=killmail_id,
                        killmail_hash=killmail_hash,
                    ),
                    params={"datasource": "tranquility"},
                    headers=self.headers,
                    timeout=self.timeout,
                )
                detail_response.raise_for_status()
                detail = detail_response.json()
                if isinstance(detail, dict) and isinstance(detail.get("victim"), dict):
                    esi = detail
            except requests.RequestException:
                pass
        if not isinstance(esi.get("victim"), dict):
            raise ValueError("KB 记录缺少被击杀方详情")
        return {"killmail_id": killmail_id, "esi": esi, "zkb": zkb}

    def query_entity(self, entity_type: str, entity_name: str) -> KbReport | None:
        if entity_type not in {"character", "corporation", "alliance"}:
            raise ValueError("不支持的 KB 实体类型")
        cache_key = f"{entity_type}:{entity_name.strip().casefold()}"
        now = time.monotonic()
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached and cached[0] > now:
                return cached[1]

        identity = self._resolve_entity(entity_type, entity_name.strip())
        if identity is None:
            report = None
        else:
            entity_id, resolved_name = identity
            stats = self._fetch_stats(entity_id, entity_type)
            report = self._build_report(entity_id, resolved_name, stats, entity_type)

        with self._cache_lock:
            self._cache[cache_key] = (now + self.cache_seconds, report)
        return report

    def _resolve_character(self, character_name: str) -> tuple[int, str] | None:
        return self._resolve_entity("character", character_name)

    def _resolve_entity(self, entity_type: str, entity_name: str) -> tuple[int, str] | None:
        response = requests.post(
            self.esi_ids_url,
            params={"datasource": "tranquility", "language": "en"},
            json=[entity_name],
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        category = {
            "character": "characters",
            "corporation": "corporations",
            "alliance": "alliances",
        }[entity_type]
        entities = payload.get(category, []) if isinstance(payload, dict) else []
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            name = str(entity.get("name", "")).strip()
            if name.casefold() != entity_name.casefold():
                continue
            try:
                return int(entity["id"]), name
            except (KeyError, TypeError, ValueError):
                continue
        return None

    def _fetch_stats(self, character_id: int, entity_type: str = "character") -> dict[str, Any]:
        url = (
            self.zkill_stats_url.format(character_id=character_id)
            if entity_type == "character"
            else self.zkill_entity_stats_url.format(
                entity_type={"corporation": "corporationID", "alliance": "allianceID"}[entity_type],
                entity_id=character_id,
            )
        )
        response = requests.get(
            url,
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("zKillboard 返回了无效数据")
        if payload.get("error"):
            if str(payload["error"]).strip().casefold() == "invalid type or id":
                return {}
            raise ValueError(str(payload["error"]))
        return payload

    def _build_report(
        self, character_id: int, character_name: str, stats: dict[str, Any],
        entity_type: str = "character",
    ) -> KbReport:
        info = stats.get("info") if isinstance(stats.get("info"), dict) else {}
        corporation_id = self._positive_int(info.get("corporationID") or info.get("corporation_id"))
        alliance_id = self._positive_int(info.get("allianceID") or info.get("alliance_id"))
        names = (
            self._resolve_names([value for value in (corporation_id, alliance_id) if value])
            if entity_type == "character"
            else {}
        )
        security_status = (
            self._optional_float(info.get("security_status", info.get("secStatus")))
            if entity_type == "character" else None
        )
        return KbReport(
            character_id=character_id,
            character_name=str(info.get("name") or character_name),
            corporation_name=names.get(corporation_id),
            alliance_name=names.get(alliance_id),
            security_status=security_status,
            danger_ratio=self._number(stats.get("dangerRatio")),
            gang_ratio=self._number(stats.get("gangRatio")),
            ships_destroyed=self._integer(stats.get("shipsDestroyed")),
            ships_lost=self._integer(stats.get("shipsLost")),
            isk_destroyed=self._number(stats.get("iskDestroyed")),
            isk_lost=self._number(stats.get("iskLost")),
            solo_kills=self._integer(stats.get("soloKills")),
            solo_losses=self._integer(stats.get("soloLosses")),
            entity_type=entity_type,
        )

    def _resolve_names(self, entity_ids: list[int]) -> dict[int, str]:
        if not entity_ids:
            return {}
        # ESI requires every ID in a batch to be unique. Keep first-seen order so
        # callers can pass overlapping identity fields without triggering a 400.
        unique_ids: list[int] = []
        seen_ids: set[int] = set()
        for value in entity_ids:
            entity_id = self._positive_int(value)
            if entity_id is not None and entity_id not in seen_ids:
                seen_ids.add(entity_id)
                unique_ids.append(entity_id)
        if not unique_ids:
            return {}
        resolved: dict[int, str] = {}

        def fetch(ids: list[int]) -> None:
            response = requests.post(
                self.esi_names_url,
                params={"datasource": "tranquility"},
                json=ids,
                headers=self.headers,
                timeout=self.timeout,
            )
            if response.status_code == 400 and len(ids) > 1:
                # ESI rejects a batch containing a retired/unknown entity ID.
                # Split only on this validation error so valid participants still resolve.
                midpoint = len(ids) // 2
                fetch(ids[:midpoint])
                fetch(ids[midpoint:])
                return
            if response.status_code == 400:
                return
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                return
            for item in payload:
                if not isinstance(item, dict):
                    continue
                entity_id = self._positive_int(item.get("id"))
                name = str(item.get("name", "")).strip()
                if entity_id and name:
                    resolved[entity_id] = name

        fetch(unique_ids)
        return resolved

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        try:
            result = int(value)
        except (TypeError, ValueError):
            return None
        return result if result > 0 else None

    @staticmethod
    def _integer(value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _number(value: Any) -> float:
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
