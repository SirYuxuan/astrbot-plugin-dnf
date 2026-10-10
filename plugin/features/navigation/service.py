"""导航指令解析与逐角色结果展示。"""

import asyncio
import re
import shlex

import requests

from ..rat.client import EVE_BINDING_HINT
from .client import WaypointApiError, WaypointClient


class NavigationFeature:
    USAGE = '用法：/nav <角色名|ALL> <星系>；名称含空格时请加英文引号，例如 /nav "Yuxan Axiom" "New Caldari"'

    def __init__(self, client: WaypointClient) -> None:
        self.client = client

    async def query(self, command: str, qq: str) -> str:
        text = re.sub(r"^/?nav(?:\s+|$)", "", command.strip(), count=1).strip()
        if not text:
            return self.USAGE
        try:
            parts = shlex.split(text)
        except ValueError:
            return self.USAGE
        if len(parts) < 2:
            return self.USAGE
        if parts[0].casefold() == "all":
            character_name = "ALL"
            destination = " ".join(parts[1:])
        else:
            character_name = " ".join(parts[:-1])
            destination = parts[-1]
        if not character_name or not destination:
            return self.USAGE
        if not re.fullmatch(r"[1-9]\d{4,11}", qq.strip()):
            return "无法获取有效的用户 QQ"
        try:
            data = await asyncio.to_thread(
                self.client.set_waypoint, qq.strip(), character_name, destination
            )
            return self._format_result(destination, data)
        except WaypointApiError as error:
            return self._format_error(error)
        except requests.RequestException:
            return "EVE 导航接口暂时不可用，请稍后重试。"
        except ValueError:
            return "EVE 导航接口返回了无效数据，请稍后重试。"

    @staticmethod
    def _format_error(error: WaypointApiError) -> str:
        message = error.message.strip()
        if error.status == 429:
            return "导航请求过于频繁，请稍后重试。"
        if "QQ" in message and any(word in message for word in ("未绑定", "找不到", "不存在")):
            return EVE_BINDING_HINT
        if error.status == 404 and any(word in message for word in ("目的地", "星系")):
            return "目的地星系不存在，请检查名称或 ID。"
        if any(word in message for word in ("角色找不到", "角色不存在", "未找到角色")):
            return "没有找到指定角色，请检查角色名及 QQ 绑定。"
        return f"EVE 导航失败：{message}"

    @staticmethod
    def _format_result(destination: str, data: dict) -> str:
        name = str(data.get("destinationName") or destination).strip()
        characters = data["characters"]
        if not characters:
            raise ValueError("导航接口没有返回角色结果")
        succeeded = sum(
            item.get("success") is True for item in characters if isinstance(item, dict)
        )
        failed = len(characters) - succeeded
        lines = [f"EVE 导航：{name}（成功 {succeeded}，失败 {failed}）"]
        for item in characters:
            if not isinstance(item, dict):
                raise ValueError("导航接口返回了无效角色结果")
            character = str(item.get("characterName") or "未知角色").strip()
            message = str(item.get("message") or "").strip()
            if item.get("success") is True:
                lines.append(f"✅ {character}：{message or '导航已设置'}")
            else:
                lines.append(f"❌ {character}：{message or '设置失败，请检查角色授权与客户端状态'}")
        return "\n".join(lines)
