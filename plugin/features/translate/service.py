"""翻译命令解析与结果格式化。"""

import asyncio
import re

import requests

from .client import TranslateApiError, TranslateClient

KINDS = (
    "type",
    "marketGroup",
    "group",
    "category",
    "solarSystem",
    "constellation",
    "region",
)
KIND_LOOKUP = {kind.casefold(): kind for kind in KINDS}


class TranslateFeature:
    USAGE = "用法：/tr 名称（可选：/tr kind=type 名称）"

    def __init__(self, client: TranslateClient) -> None:
        self.client = client

    async def query(self, command: str) -> str:
        text = re.sub(r"^/?tr(?:\s+|$)", "", command.strip(), count=1).strip()
        if not text:
            return self.USAGE
        kind = None
        if text.casefold().startswith("kind="):
            parts = text.split(maxsplit=1)
            token = parts[0]
            text = parts[1] if len(parts) == 2 else ""
            kind = KIND_LOOKUP.get(token[5:].casefold())
            text = text.strip()
            if kind is None:
                return "不支持的分类。可用：" + "、".join(KINDS)
            if not text:
                return self.USAGE
        try:
            data = await asyncio.to_thread(self.client.lookup, text, kind)
            return self._format_result(text, data)
        except requests.RequestException:
            return "EVE 名称翻译接口暂时不可用，请稍后重试。"
        except (ValueError, TranslateApiError) as error:
            return f"EVE 名称翻译失败：{error}"

    @staticmethod
    def _format_result(query: str, data: dict) -> str:
        matches = data["matches"]
        if not matches:
            return f"没有找到“{query}”的 EVE 名称翻译。"
        target = str(data.get("targetLanguage") or "").casefold()
        source_key = (
            "nameZh" if str(data.get("sourceLanguage") or "").casefold() == "zh" else "nameEn"
        )
        rows = []
        for match in matches:
            if not isinstance(match, dict):
                raise ValueError("翻译接口返回了无效候选")
            translated = str(match.get("translation") or "").strip()
            name = str(match.get(source_key) or query).strip()
            kind = str(match.get("kind") or "未知分类").strip()
            entity_id = match.get("id")
            if not translated or entity_id is None:
                raise ValueError("翻译接口返回了不完整的候选")
            rows.append(f"{name} → {translated}（{kind} ID {entity_id}）")
        if len(rows) == 1:
            return f"EVE 名称翻译：{rows[0]}"
        direction = "中→英" if target == "en" else "英→中" if target == "zh" else "双语"
        return f"找到 {len(rows)} 个候选（{direction}）：\n" + "\n".join(
            f"{index}. {row}" for index, row in enumerate(rows, 1)
        )
