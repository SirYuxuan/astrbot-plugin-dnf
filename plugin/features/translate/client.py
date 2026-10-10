"""EVE 公共名称翻译接口。"""

from typing import Any

import requests


class TranslateApiError(Exception):
    """远端接口返回了可展示的业务错误。"""


class TranslateClient:
    DEFAULT_URL = "https://admin-api.oofo.cc/game/eve/public/translate"

    def __init__(self, url: str = DEFAULT_URL, timeout: int = 10) -> None:
        self.url = url.strip()
        self.timeout = max(1, timeout)

    def lookup(self, name: str, kind: str | None = None) -> dict[str, Any]:
        params = {"q": name}
        if kind:
            params["kind"] = kind
        response = requests.get(self.url, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("翻译接口返回了无效数据")
        if payload.get("code") != 0:
            raise TranslateApiError(str(payload.get("message") or "翻译查询失败"))
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("matches"), list):
            raise ValueError("翻译接口缺少匹配结果")
        return data
