from __future__ import annotations

import asyncio
import re

from ..rat.client import EVE_BINDING_HINT
from .client import LpClient


class LpFeature:
    def __init__(self, client: LpClient) -> None:
        self.client = client

    async def query(self, command: str, qq: str) -> str:
        character = re.sub(r"^/?lp(?:\s+|$)", "", command.strip(), count=1).strip()
        if not re.fullmatch(r"[1-9]\d{4,11}", qq.strip()):
            return "无法获取有效的用户 QQ"
        if len(character) > 100:
            return "角色名过长，请检查后重试"
        try:
            result = await asyncio.to_thread(self.client.query, qq.strip(), character or None)
        except Exception:
            return "LP 收益查询失败，请稍后重试。"
        return result or EVE_BINDING_HINT
