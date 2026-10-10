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

    @property
    def has_activity(self) -> bool:
        return bool(self.ships_destroyed or self.ships_lost or self.isk_destroyed or self.isk_lost)


class KbClient:
    ESI_IDS_URL = "https://esi.evetech.net/latest/universe/ids/"
    ESI_NAMES_URL = "https://esi.evetech.net/latest/universe/names/"
    ZKILL_STATS_URL = "https://zkillboard.com/api/stats/characterID/{character_id}/kills/"

    def __init__(
        self,
        *,
        timeout: int = 15,
        cache_seconds: int = 600,
        user_agent: str = "astrbot-plugin-dnf/1.7",
        esi_ids_url: str = ESI_IDS_URL,
        esi_names_url: str = ESI_NAMES_URL,
        zkill_stats_url: str = ZKILL_STATS_URL,
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
        self._cache: dict[str, tuple[float, KbReport | None]] = {}
        self._cache_lock = threading.Lock()

    def query(self, character_name: str) -> KbReport | None:
        cache_key = character_name.strip().casefold()
        now = time.monotonic()
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached and cached[0] > now:
                return cached[1]

        identity = self._resolve_character(character_name.strip())
        if identity is None:
            report = None
        else:
            character_id, resolved_name = identity
            stats = self._fetch_stats(character_id)
            report = self._build_report(character_id, resolved_name, stats)

        with self._cache_lock:
            self._cache[cache_key] = (now + self.cache_seconds, report)
        return report

    def _resolve_character(self, character_name: str) -> tuple[int, str] | None:
        response = requests.post(
            self.esi_ids_url,
            params={"datasource": "tranquility", "language": "en"},
            json=[character_name],
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        characters = payload.get("characters", []) if isinstance(payload, dict) else []
        for character in characters:
            if not isinstance(character, dict):
                continue
            name = str(character.get("name", "")).strip()
            if name.casefold() != character_name.casefold():
                continue
            try:
                return int(character["id"]), name
            except (KeyError, TypeError, ValueError):
                continue
        return None

    def _fetch_stats(self, character_id: int) -> dict[str, Any]:
        response = requests.get(
            self.zkill_stats_url.format(character_id=character_id),
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("zKillboard 返回了无效数据")
        if payload.get("error"):
            raise ValueError(str(payload["error"]))
        return payload

    def _build_report(
        self, character_id: int, character_name: str, stats: dict[str, Any]
    ) -> KbReport:
        info = stats.get("info") if isinstance(stats.get("info"), dict) else {}
        corporation_id = self._positive_int(info.get("corporationID") or info.get("corporation_id"))
        alliance_id = self._positive_int(info.get("allianceID") or info.get("alliance_id"))
        names = self._resolve_names([value for value in (corporation_id, alliance_id) if value])
        security_status = self._optional_float(info.get("security_status", info.get("secStatus")))
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
        )

    def _resolve_names(self, entity_ids: list[int]) -> dict[int, str]:
        if not entity_ids:
            return {}
        response = requests.post(
            self.esi_names_url,
            params={"datasource": "tranquility"},
            json=entity_ids,
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            return {}
        resolved: dict[int, str] = {}
        for item in payload:
            if not isinstance(item, dict):
                continue
            entity_id = self._positive_int(item.get("id"))
            name = str(item.get("name", "")).strip()
            if entity_id and name:
                resolved[entity_id] = name
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
