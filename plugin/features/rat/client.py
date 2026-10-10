import json
from typing import Any

import requests

EVE_BINDING_HINT = "没有找到角色。请先注册eve.oofo.cc 绑定角色和绑定QQ后使用。"


class RatClient:
    """按 QQ 查询远端接口；具体接口信息通过配置注入。"""

    DEFAULT_URL = "https://admin-api.oofo.cc/game/eve/public/users/by-qq/{qq}/ratting-report"

    def __init__(self, url: str | None = None, timeout: int = 10) -> None:
        self.url = (self.DEFAULT_URL if url is None else url).strip()
        self.timeout = max(1, timeout)

    def query(self, qq: str) -> str:
        if not self.url:
            return "rat 接口尚未配置"

        url = self.url.format(qq=qq)
        response = requests.get(url, timeout=self.timeout)
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
            if payload.get("message"):
                return str(payload["message"])
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, ensure_ascii=False, indent=2)
