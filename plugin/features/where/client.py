"""按 QQ 搜索已同步的角色资产。"""

import requests


class AssetSearchError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class AssetSearchClient:
    DEFAULT_URL = "https://admin-api.oofo.cc/game/eve/public/users/by-qq/{qq}/assets/search"

    def __init__(self, url: str = DEFAULT_URL, timeout: int = 15) -> None:
        self.url = url.strip()
        self.timeout = max(1, timeout)

    def search(self, qq: str, keyword: str, page: int) -> dict:
        response = requests.get(
            self.url.format(qq=qq),
            params={"keyword": keyword, "page": page},
            timeout=self.timeout,
        )
        try:
            payload = response.json()
        except ValueError:
            raise AssetSearchError(response.status_code, "资产接口暂时不可用") from None
        if not isinstance(payload, dict):
            raise ValueError("资产接口返回了无效数据")
        if not response.ok or payload.get("code") != 0:
            raise AssetSearchError(
                response.status_code, str(payload.get("message") or "资产查询失败")
            )
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise ValueError("资产接口缺少查询结果")
        return data
