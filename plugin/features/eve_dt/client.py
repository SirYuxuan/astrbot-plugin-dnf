from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import requests


@dataclass(frozen=True)
class EveServerStatus:
    start_time: datetime
    players: int
    vip: bool


class EveStatusClient:
    DEFAULT_URL = "https://esi.evetech.net/latest/status/"

    def __init__(
        self,
        *,
        url: str = DEFAULT_URL,
        timeout: int = 10,
        user_agent: str = "astrbot-plugin-dnf/1.7",
    ) -> None:
        self.url = url
        self.timeout = max(1, timeout)
        self.headers = {
            "User-Agent": user_agent.strip() or "astrbot-plugin-dnf/1.7",
            "Accept-Encoding": "gzip",
        }

    def status(self) -> EveServerStatus:
        response = requests.get(
            self.url,
            params={"datasource": "tranquility"},
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("ESI 状态接口返回了无效数据")
        raw_start_time = str(payload.get("start_time", "")).strip()
        if not raw_start_time:
            raise ValueError("ESI 状态接口缺少 start_time")
        try:
            start_time = datetime.fromisoformat(raw_start_time.replace("Z", "+00:00"))
            players = int(payload["players"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("ESI 状态接口字段无效") from error
        if start_time.tzinfo is None:
            raise ValueError("ESI 状态接口的 start_time 缺少时区")
        return EveServerStatus(
            start_time=start_time,
            players=max(0, players),
            vip=bool(payload.get("vip", False)),
        )
