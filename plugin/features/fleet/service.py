"""舰队邀请指令。"""

import asyncio
import re
import shlex

import requests

from ..rat.client import EVE_BINDING_HINT
from .client import FleetInviteClient, FleetInviteError


class FleetFeature:
    USAGE = '用法：/fleet "主角色名" ALL 或 /fleet "主角色名" "目标角色名"'

    def __init__(self, client: FleetInviteClient) -> None:
        self.client = client

    async def query(self, command: str, qq: str) -> str:
        text = re.sub(r"^/?fleet(?:\s+|$)", "", command.strip(), count=1).strip()
        try:
            parts = shlex.split(text)
        except ValueError:
            return self.USAGE
        if len(parts) != 2 or not all(parts):
            return self.USAGE
        if not re.fullmatch(r"[1-9]\d{4,11}", qq.strip()):
            return "无法获取有效的用户 QQ"
        try:
            data = await asyncio.to_thread(self.client.invite, qq.strip(), parts[0], parts[1])
        except FleetInviteError as error:
            if error.status == 404 and "没有找到该QQ号的EVE绑定信息" in error.message:
                return EVE_BINDING_HINT
            if error.status == 429:
                return "舰队邀请过于频繁，请稍后重试。"
            return f"舰队邀请失败：{error.message}"
        except requests.RequestException:
            return "舰队接口暂时不可用，请稍后重试。"
        except ValueError:
            return "舰队接口返回了无效数据，请稍后重试。"
        characters = data["characters"]
        lines = [
            f"舰队邀请：{data.get('mainCharacter') or parts[0]} "
            f"（成功 {data.get('succeeded', 0)}，失败 {data.get('failed', 0)}）"
        ]
        for item in characters:
            if isinstance(item, dict):
                prefix = "已发送" if item.get("success") else "失败"
                lines.append(
                    f"{prefix} · {item.get('characterName') or '未知角色'}：{item.get('message') or ''}"
                )
        return "\n".join(lines)
