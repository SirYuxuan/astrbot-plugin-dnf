import asyncio
import re

from .client import RatClient


class RatFeature:
    def __init__(self, client: RatClient) -> None:
        self.client = client

    async def query(self, qq: str) -> str:
        qq = qq.strip()
        if not re.fullmatch(r"[1-9]\d{4,11}", qq):
            return "无法获取有效的用户 QQ"
        result = await asyncio.to_thread(self.client.query, qq)
        return result or "接口未返回内容"
