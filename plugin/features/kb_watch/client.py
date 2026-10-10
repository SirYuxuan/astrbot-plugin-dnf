from __future__ import annotations

from typing import Any

import requests


class ZkillLiveClient:
    DEFAULT_SEQUENCE_URL = "https://r2z2.zkillboard.com/ephemeral/sequence.json"
    DEFAULT_EPHEMERAL_URL = "https://r2z2.zkillboard.com/ephemeral/{sequence}.json"
    DEFAULT_NAMES_URL = "https://esi.evetech.net/latest/universe/names/"

    def __init__(
        self,
        *,
        timeout: int = 10,
        user_agent: str = "astrbot-plugin-dnf/1.7",
        sequence_url: str = DEFAULT_SEQUENCE_URL,
        ephemeral_url: str = DEFAULT_EPHEMERAL_URL,
        names_url: str = DEFAULT_NAMES_URL,
    ) -> None:
        self.timeout = max(1, timeout)
        self.headers = {
            "User-Agent": user_agent.strip() or "astrbot-plugin-dnf/1.7",
            "Accept-Encoding": "gzip",
        }
        self.sequence_url = sequence_url
        self.ephemeral_url = ephemeral_url
        self.names_url = names_url

    def latest_sequence(self) -> int:
        response = requests.get(
            self.sequence_url,
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        try:
            sequence = int(payload["sequence"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("zKillboard 实时序号无效") from error
        if sequence <= 0:
            raise ValueError("zKillboard 实时序号无效")
        return sequence

    def package(self, sequence: int) -> dict[str, Any] | None:
        response = requests.get(
            self.ephemeral_url.format(sequence=sequence),
            headers=self.headers,
            timeout=self.timeout,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("esi"), dict):
            raise ValueError("zKillboard 实时击杀数据无效")
        return payload

    def names(self, entity_ids: list[int]) -> dict[int, str]:
        ids = set()
        for value in entity_ids:
            try:
                entity_id = int(value)
            except (TypeError, ValueError):
                continue
            if entity_id > 0:
                ids.add(entity_id)
        ids = sorted(ids)
        if not ids:
            return {}
        response = requests.post(
            self.names_url,
            params={"datasource": "tranquility"},
            json=ids,
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            return {}
        resolved = {}
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                entity_id = int(item["id"])
            except (KeyError, TypeError, ValueError):
                continue
            name = str(item.get("name", "")).strip()
            if name:
                resolved[entity_id] = name
        return resolved
