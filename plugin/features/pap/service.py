"""Async PAP command handlers and conservative public response formatting."""

import asyncio
import json
import logging
import math
import re

import requests

from .client import PapClient

logger = logging.getLogger(__name__)
PAP_BINDING_HINT = "请前往军团系统绑定，https://dijiuren.top"


class PapFeature:
    def __init__(self, client: PapClient):
        self.client = client

    async def query(self, qq: str) -> str:
        qq = qq.strip()
        if not re.fullmatch(r"[1-9]\d{4,11}", qq):
            return "无法获取有效的用户 QQ"
        return await self._query(self.client.query, qq)

    async def ranking(self) -> str:
        return await self._query(self.client.ranking, ranking=True)

    async def _query(self, method, *args, ranking=False):
        try:
            payload = await asyncio.to_thread(method, *args)
            return self.format_response(payload, ranking=ranking)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            logger.warning("PAP 接口 HTTP 错误: %s", status)
            if status == 404:
                return "PAP 接口暂不可用（HTTP 404），请联系管理员检查接口地址。"
            return "PAP 查询失败，请稍后重试。"
        except (requests.RequestException, ValueError):
            logger.exception("PAP 查询失败")
            return "PAP 查询失败，请稍后重试。"

    @staticmethod
    def format_response(payload, *, ranking=False):
        if isinstance(payload, str):
            return payload.strip() or "暂无 PAP 数据。"
        if isinstance(payload, dict):
            code = payload.get("code")
            if not ranking and (code == 40400 or payload.get("message") == "资源不存在"):
                return PAP_BINDING_HINT
            if code is not None and code != 0:
                return str(payload.get("message") or "PAP 查询失败。")
            data = payload.get("data", payload)
            if isinstance(data, dict) and isinstance(data.get("message"), str):
                return data["message"].strip() or "暂无 PAP 数据。"
            if isinstance(data, str):
                return data.strip() or "暂无 PAP 数据。"
            if data is None or data == [] or data == {}:
                return "暂无 PAP 数据。"
            if ranking:
                return PapFeature._format_ranking(data)
            return PapFeature._format_user(data)
        if not payload:
            return "暂无 PAP 数据。"
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _amount(value):
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise ValueError("PAP 数值缺失或无效")
        return f"{value:,}"

    @staticmethod
    def _format_user(data):
        if not isinstance(data, dict):
            raise ValueError("PAP 个人数据无效")
        count = data.get("characterCount")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError("PAP 角色数缺失或无效")
        nickname = " ".join(str(data.get("nickname") or "未设置昵称").split())
        lines = ["【个人 PAP】", f"昵称：{nickname}", f"角色数：{count}"]
        for label, key in [
            ("可用 PAP", "available"),
            ("冻结 PAP", "frozen"),
            ("累计获得", "income"),
            ("累计使用", "spent"),
        ]:
            lines.append(f"{label}：{PapFeature._amount(data.get(key))}")
        return "\n".join(lines)

    @staticmethod
    def _format_ranking(data):
        if not isinstance(data, list):
            raise ValueError("PAP 排行榜缺少列表")
        if not data:
            return "暂无 PAP 排行数据。"
        rows = []
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("PAP 排行榜条目无效")
            rank, income = item.get("rank"), item.get("income")
            if (
                not isinstance(rank, int)
                or isinstance(rank, bool)
                or rank < 1
                or not isinstance(income, (int, float))
                or isinstance(income, bool)
            ):
                raise ValueError("PAP 排行榜缺少排名或累计获得")
            nickname = " ".join(str(item.get("nickname") or "未设置昵称").split())
            rows.append((rank, nickname, income))
        rows.sort(key=lambda row: row[0])
        return "【PAP 累计获得 Top10】\n" + "\n".join(
            f"{rank}. {nickname}：{PapFeature._amount(income)} PAP"
            for rank, nickname, income in rows[:10]
        )
