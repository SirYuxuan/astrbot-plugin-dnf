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
        character_name = re.sub(r"^/?kb(?:\s+|$)", "", message.strip(), count=1).strip()
        if not character_name:
            return "用法：/kb 角色名\n示例：/kb Yuxan Axiom"
        if len(character_name) > 100:
            return "角色名过长，请检查后重试"
        try:
            report = await asyncio.to_thread(self.client.query, character_name)
        except (requests.RequestException, ValueError):
            logger.exception("KB 查询上游接口异常: character=%s", character_name)
            return "KB查询失败，请稍后重试"
        if report is None:
            return f"未找到角色：{character_name}\n请检查角色名是否完整，角色名支持空格。"
        return self.format_report(report)

    @classmethod
    def format_report(cls, report: KbReport) -> str:
        detail_url = f"https://zkillboard.com/character/{report.character_id}/"
        if not report.has_activity:
            return (
                f"【KB 查询】{report.character_name}\n"
                f"该角色暂无公开的击杀或损失记录。\n详情：{detail_url}"
            )
        lines = [f"【KB 查询】{report.character_name}"]
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
