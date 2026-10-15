"""配置导入接口；写入请求不自动重试。"""

import requests


class FittingImportError(Exception):
    pass


class FittingClient:
    DEFAULT_URL = "https://admin-api.oofo.cc/game/eve/public/users/by-qq/{qq}/fittings"

    def __init__(self, url: str = DEFAULT_URL, timeout: int = 20):
        self.url = url
        self.timeout = max(1, timeout)

    def import_fitting(self, qq: str, character: str, fitting: str) -> None:
        response = requests.post(
            self.url.format(qq=qq),
            json={"characterName": character, "fittingText": fitting},
            timeout=self.timeout,
            allow_redirects=False,
        )
        try:
            payload = response.json()
        except ValueError:
            raise FittingImportError("接口返回异常，导入结果待确认，请先在游戏中检查。") from None
        if not isinstance(payload, dict):
            raise FittingImportError("接口返回异常，导入结果待确认，请先在游戏中检查。")
        if not 200 <= response.status_code < 300 or payload.get("code") != 0:
            raise FittingImportError(str(payload.get("message") or "接口拒绝导入")[:500])
