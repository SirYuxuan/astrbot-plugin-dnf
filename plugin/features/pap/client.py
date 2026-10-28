"""Read PAP reports without embedding local balance calculations."""

import requests


class PapClient:
    USER_URL = "https://dijiuren.top/api/game/eve/public/pap/users/by-qq/{qq}"
    RANKING_URL = "https://dijiuren.top/api/game/eve/public/pap/ranking"

    def __init__(self, user_url=USER_URL, ranking_url=RANKING_URL, timeout=15):
        self.user_url = user_url.strip()
        self.ranking_url = ranking_url.strip()
        self.timeout = max(1, timeout)

    def query(self, qq):
        return self._get(self.user_url.format(qq=qq))

    def ranking(self):
        return self._get(self.ranking_url)

    def _get(self, url):
        if not url:
            raise ValueError("PAP 接口尚未配置")
        response = requests.get(url, timeout=self.timeout)
        if response.status_code == 404:
            try:
                error = response.json()
            except ValueError:
                error = None
            if isinstance(error, dict) and error.get("code") == 40400:
                return error
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, (dict, list, str)):
            raise ValueError("PAP 接口返回了无效数据")
        return payload
