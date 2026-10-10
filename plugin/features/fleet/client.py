"""舰队邀请公开接口客户端。"""

import requests


class FleetInviteError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class FleetInviteClient:
    DEFAULT_URL = "https://admin-api.oofo.cc/game/eve/public/users/by-qq/{qq}/fleet/invitations"

    def __init__(self, url: str = DEFAULT_URL, timeout: int = 30) -> None:
        self.url = url.strip()
        self.timeout = max(1, timeout)

    def invite(self, qq: str, main_character: str, target: str) -> dict:
        response = requests.post(
            self.url.format(qq=qq),
            json={"mainCharacter": main_character, "target": target},
            timeout=self.timeout,
        )
        try:
            payload = response.json()
        except ValueError:
            raise FleetInviteError(response.status_code, "舰队接口暂时不可用") from None
        if not isinstance(payload, dict):
            raise ValueError("舰队接口返回了无效数据")
        if not response.ok or payload.get("code") != 0:
            raise FleetInviteError(
                response.status_code, str(payload.get("message") or "舰队邀请失败")
            )
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("characters"), list):
            raise ValueError("舰队接口缺少角色结果")
        return data
