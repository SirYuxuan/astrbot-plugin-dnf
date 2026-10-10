from __future__ import annotations

import asyncio
import logging
import re

import requests

from .client import KbClient, KbReport

logger = logging.getLogger(__name__)


class KbFeature:
    def __init__(self, client: KbClient) -> None:
        self.client = client

    async def query(self, message: str) -> str:
        query = re.sub(r"^/?kb(?:\s+|$)", "", message.strip(), count=1).strip()
        if not query:
            return "用法：/kb 角色名｜/kb 军团 军团名｜/kb 联盟 联盟名"
        entity_type = "character"
        kinds = {
            "军团": "corporation",
            "corporation": "corporation",
            "联盟": "alliance",
            "alliance": "alliance",
            "角色": "character",
            "character": "character",
        }
        parts = query.split(maxsplit=1)
        prefix, name = parts[0], parts[1] if len(parts) > 1 else ""
        if prefix.casefold() in kinds:
            if not name.strip():
                return f"请在 {prefix} 后输入完整名称"
            entity_type = kinds[prefix.casefold()]
            query = name.strip()
        if len(query) > 100:
            return "名称过长，请检查后重试"
        try:
            if entity_type == "character":
                report = await asyncio.to_thread(self.client.query, query)
            else:
                report = await asyncio.to_thread(self.client.query_entity, entity_type, query)
        except (requests.RequestException, ValueError):
            logger.exception("KB 查询上游接口异常: type=%s name=%s", entity_type, query)
            return "KB查询失败，请稍后重试"
        if report is None:
            label = {"character": "角色", "corporation": "军团", "alliance": "联盟"}[entity_type]
            return f"未找到{label}：{query}\n请检查名称是否完整，名称支持空格。"
        return self.format_report(report)

    @classmethod
    def format_report(cls, report: KbReport) -> str:
        label = {"character": "角色", "corporation": "军团", "alliance": "联盟"}[
            report.entity_type
        ]
        title = "KB 查询" if report.entity_type == "character" else f"{label} KB"
        detail_url = f"https://zkillboard.com/{report.entity_type}/{report.character_id}/"
        if not report.has_activity:
            return (
                f"【{title}】{report.character_name}\n"
                f"该{label}暂无公开的击杀或损失记录。\n详情：{detail_url}"
            )
        lines = [f"【{title}】{report.character_name}"]
        if report.corporation_name:
            lines.append(f"军团：{report.corporation_name}")
        if report.alliance_name:
            lines.append(f"联盟：{report.alliance_name}")
        if report.security_status is not None:
            lines.append(f"安全等级：{report.security_status:.2f}")
        lines.extend(
            (
                f"威胁度：{report.danger_ratio:.0f}%｜团战率：{report.gang_ratio:.0f}%",
                f"击杀：{report.ships_destroyed:,} 艘｜{cls._format_isk(report.isk_destroyed)}",
                f"损失：{report.ships_lost:,} 艘｜{cls._format_isk(report.isk_lost)}",
                f"单杀：{report.solo_kills:,}｜单独损失：{report.solo_losses:,}",
                f"ISK 击损比：{cls._ratio(report.isk_destroyed, report.isk_lost)}｜"
                f"舰船击损比：{cls._ratio(report.ships_destroyed, report.ships_lost)}",
                f"详情：{detail_url}",
            )
        )
        return "\n".join(lines)

    @staticmethod
    def _format_isk(value: float) -> str:
        for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if value >= threshold:
                return f"{value / threshold:.2f} {suffix} ISK"
        return f"{value:.0f} ISK"

    @staticmethod
    def _ratio(won: float, lost: float) -> str:
        if lost <= 0:
            return "∞" if won > 0 else "0.00"
        return f"{won / lost:.2f}"
