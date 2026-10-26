from __future__ import annotations

import json
from typing import Any

import requests

from ..rat.client import EVE_BINDING_HINT


class LpClient:
    DEFAULT_URL = "https://admin-api.oofo.cc/game/eve/public/users/by-qq/{qq}/lp"

    def __init__(self, url: str = DEFAULT_URL, timeout: int = 15) -> None:
        self.url = url.strip()
        self.timeout = max(1, timeout)

    def query(self, qq: str, character: str | None = None) -> str:
        if not self.url:
            return "lp 接口尚未配置"
        params = {"qq": qq}
        if character:
            params["character"] = character
        try:
            response = requests.get(
                self.url.format(qq=qq), params=params, timeout=self.timeout
            )
        except requests.RequestException:
            # Older deployments expose /lp without a {qq} path segment.
            if "{qq}" not in self.url:
                raise
            response = requests.get(self.url.replace("/{qq}", ""), params=params, timeout=self.timeout)
        response.raise_for_status()
        return self._format_response(response)

    @staticmethod
    def _format_response(response: requests.Response) -> str:
        try:
            payload: Any = response.json()
        except ValueError:
            return response.text.strip()
        if isinstance(payload, dict):
            if payload.get("code") == 46104:
                return EVE_BINDING_HINT
            if payload.get("code") == 0:
                data = payload.get("data")
                if isinstance(data, dict) and data.get("message"):
                    return str(data["message"])
                if isinstance(data, str):
                    return data
            if payload.get("message"):
                return str(payload["message"])
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, ensure_ascii=False, indent=2)
