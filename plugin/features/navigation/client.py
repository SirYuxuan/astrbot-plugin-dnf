"""按 QQ 为 EVE 角色设置航点的公开接口。"""

from typing import Any

import requests


class WaypointApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class WaypointClient:
    DEFAULT_URL = "https://admin-api.oofo.cc/game/eve/public/users/by-qq/{qq}/waypoint"

    def __init__(self, url: str = DEFAULT_URL, timeout: int = 15) -> None:
        self.url = url.strip()
        self.timeout = max(1, timeout)

    def set_waypoint(self, qq: str, character_name: str, destination: str) -> dict[str, Any]:
        response = requests.post(
            self.url.format(qq=qq),
            json={"characterName": character_name, "destination": destination},
            timeout=self.timeout,
        )
        try:
            payload = response.json()
        except ValueError:
            if not response.ok:
                raise WaypointApiError(response.status_code, "服务暂时不可用") from None
            raise ValueError("导航接口返回了无效数据") from None
        if not isinstance(payload, dict):
            raise ValueError("导航接口返回了无效数据")
        if not response.ok or payload.get("code") != 0:
            raise WaypointApiError(
                response.status_code,
                str(payload.get("message") or "导航请求失败"),
            )
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("characters"), list):
            raise ValueError("导航接口缺少角色结果")
        return data

    def set_security_agents(self, qq: str, character_name: str | None = None) -> dict[str, Any]:
        """按绑定 QQ 为全部角色或指定角色设置安全代理。"""
        url = f"{self.url.format(qq=qq).rstrip('/')}/security-agents"
        payload = {"characterName": character_name or "ALL"}
        response = requests.post(url, json=payload, timeout=self.timeout)
        try:
            body = response.json()
        except ValueError:
            if not response.ok:
                raise WaypointApiError(response.status_code, "服务暂时不可用") from None
            raise ValueError("安全代理接口返回了无效数据") from None
        if not isinstance(body, dict):
            raise ValueError("安全代理接口返回了无效数据")
        if not response.ok or body.get("code") != 0:
            raise WaypointApiError(
                response.status_code,
                str(body.get("message") or "安全代理请求失败"),
            )
        data = body.get("data")
        return data if isinstance(data, dict) else body
