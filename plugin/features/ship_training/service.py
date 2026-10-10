"""按发送者 QQ 查询舰船立即训练时间。"""

import asyncio
import re

import requests

from ..rat.client import EVE_BINDING_HINT


class ShipTrainingFeature:
    DEFAULT_URL = "https://admin-api.oofo.cc/game/eve/public/users/by-qq/{qq}/ship-training"

    def __init__(self, url: str = DEFAULT_URL, timeout: int = 15) -> None:
        self.url = url
        self.timeout = max(1, timeout)

    async def query(self, command: str, qq: str) -> str:
        ship_name = re.sub(r"^/?train(?:\s+|$)", "", command.strip(), count=1).strip()
        if not ship_name:
            return "用法：/train 乌鸦级"
        if not re.fullmatch(r"[1-9]\d{4,11}", qq.strip()):
            return "无法获取有效的用户 QQ"
        return await asyncio.to_thread(self._query, ship_name, qq.strip())

    def _query(self, ship_name: str, qq: str) -> str:
        response = requests.get(
            self.url.format(qq=qq), params={"ship": ship_name}, timeout=self.timeout
        )
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("舰船训练接口返回了无效数据")
        if payload.get("code") == 46104:
            return EVE_BINDING_HINT
        if payload.get("code") != 0:
            return str(payload.get("message") or "舰船训练查询失败")
        response.raise_for_status()
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("characters"), list):
            raise ValueError("舰船训练接口缺少角色数据")
        ship = data.get("ship") if isinstance(data.get("ship"), dict) else {}
        title = str(ship.get("name") or ship_name).strip()
        lines = [f"{title}舰船训练"]
        for character in data["characters"]:
            if not isinstance(character, dict):
                continue
            name = str(character.get("name") or "未知角色").strip()
            if character.get("error"):
                lines.append(f"{name}：{character['error']}")
            elif character.get("ready"):
                lines.append(f"{name}：已具备驾驶技能")
            elif isinstance(character.get("immediateSeconds"), (int, float)):
                seconds = max(0, int(character["immediateSeconds"]))
                missing_sp = max(0, int(character.get("missingSp") or 0))
                lines.append(f"{name}：缺 {missing_sp:,} SP｜{self._duration(seconds)}")
            else:
                lines.append(f"{name}：暂无训练时间估算")
        return "\n".join(lines)

    @staticmethod
    def _duration(seconds: int) -> str:
        minutes = (seconds + 59) // 60
        days, minutes = divmod(minutes, 1440)
        hours, minutes = divmod(minutes, 60)
        result = ""
        if days:
            result += f"{days}天"
        if hours:
            result += f"{hours}小时"
        if minutes or not result:
            result += f"{minutes}分"
        return result
