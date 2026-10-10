"""资产位置查询指令。"""

import asyncio
import re

import requests

from ..rat.client import EVE_BINDING_HINT
from .client import AssetSearchClient, AssetSearchError


class WhereFeature:
    USAGE = "用法：/where 物品名 [page=页码]，例如 /where 乌鸦级"

    def __init__(self, client: AssetSearchClient) -> None:
        self.client = client

    async def query(self, command: str, qq: str) -> str:
        text = re.sub(r"^/?where(?:\s+|$)", "", command.strip(), count=1).strip()
        if not text:
            return self.USAGE
        page = 1
        match = re.search(r"\s+page=(\d+)$", text, re.IGNORECASE)
        if match:
            page = int(match.group(1))
            text = text[: match.start()].strip()
        if not text or not 1 <= page <= 10000:
            return self.USAGE
        if not re.fullmatch(r"[1-9]\d{4,11}", qq.strip()):
            return "无法获取有效的用户 QQ"
        try:
            data = await asyncio.to_thread(self.client.search, qq.strip(), text, page)
        except AssetSearchError as error:
            if error.status == 404:
                return EVE_BINDING_HINT
            return f"资产查询失败：{error.message}"
        except requests.RequestException:
            return "资产接口暂时不可用，请稍后重试。"
        except ValueError:
            return "资产接口返回了无效数据，请稍后重试。"
        items = data["items"]
        total = int(data.get("total") or 0)
        if not items:
            return f"没有找到“{text}”的资产。"
        lines = [f"资产位置：{text}（共 {total} 条，第 {page} 页）"]
        for item in items:
            if not isinstance(item, dict):
                continue
            location = str(item.get("locationName") or "地点未解析")
            container = str(item.get("containerName") or "")
            if container:
                location += f" / {container}"
            lines.append(
                f"{item.get('characterName') or '未知角色'} · {item.get('typeName') or '未知物品'} "
                f"×{item.get('quantity') or 0} · {location}"
            )
        if page * 20 < total:
            lines.append(f"下一页：/where {text} page={page + 1}")
        lines.append("数据来自最近一次资产同步。")
        return "\n".join(lines)
