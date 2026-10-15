from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
from dataclasses import dataclass

import requests

from .client import KbClient, KbReport
from .renderer import KbKillmailRenderer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KbImageReply:
    text: str
    html: str = ""


class KbFeature:
    def __init__(
        self, client: KbClient, renderer: KbKillmailRenderer | None = None
    ) -> None:
        self.client = client
        self.renderer = renderer

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

    async def query_recent(self, message: str, activity: str) -> KbImageReply:
        command = "/kbk" if activity == "kills" else "/kbl"
        query = re.sub(r"^/?(?:kbk|kbl)(?:\s+|$)", "", message.strip(), count=1).strip()
        if activity not in {"kills", "losses"}:
            return KbImageReply("KB 记录类型无效。")
        if not query or len(query) > 100:
            return KbImageReply(f"用法：{command} 角色名")
        title = "角色最近击杀" if activity == "kills" else "角色最近损失"
        try:
            identity = await asyncio.to_thread(self.client.resolve_character, query)
        except (requests.RequestException, ValueError):
            logger.exception("KB 角色名解析失败: name=%s", query)
            return KbImageReply("KB 角色名解析失败，请稍后重试。")
        if identity is None:
            return KbImageReply(f"未找到角色：{query}\n请检查角色名是否完整，名称支持空格。")
        character_id, _resolved_name = identity
        try:
            package = await asyncio.to_thread(
                self.client.latest_character_killmail, character_id, activity
            )
        except (requests.RequestException, ValueError):
            logger.exception("KB 最近记录查询失败: name=%s id=%s activity=%s", query, character_id, activity)
            return KbImageReply("KB 最近记录查询失败，请稍后重试。")
        if package is None:
            kind = "击杀" if activity == "kills" else "损失"
            return KbImageReply(f"角色 {query} 暂无公开的最近{kind}记录。")
        text = await asyncio.to_thread(self._format_recent_text, package, title)
        if self.renderer is None:
            return KbImageReply(text)
        try:
            markup = await asyncio.to_thread(self.renderer.render, package, title)
        except Exception:
            logger.exception("KB 最近记录图片构造失败: id=%s", character_id)
            return KbImageReply(text)
        return KbImageReply(text=text, html=markup)

    def _format_recent_text(self, package: dict, title: str) -> str:
        esi = package.get("esi") if isinstance(package.get("esi"), dict) else {}
        victim = esi.get("victim") if isinstance(esi.get("victim"), dict) else {}
        character_id = self._positive_int(victim.get("character_id")) or 0
        system_id = self._positive_int(esi.get("solar_system_id")) or 0
        ship_type_id = self._positive_int(victim.get("ship_type_id")) or 0
        try:
            names = self.client.names([character_id, system_id])
        except requests.RequestException:
            names = {}
        character_name = names.get(character_id, f"角色 {character_id}")
        system_name = names.get(system_id, f"星系 {system_id}" if system_id else "未知星系")
        zkb = package.get("zkb") if isinstance(package.get("zkb"), dict) else {}
        value = self._number(zkb.get("totalValue"))
        killmail_id = self._positive_int(package.get("killmail_id")) or 0
        timestamp = self._parse_recent_time(str(esi.get("killmail_time", "")))
        return (
            f"【{title}】{character_name}\n"
            f"舰船 Type ID：{ship_type_id}\n"
            f"地点：{system_name}\n"
            f"时间：{timestamp}\n"
            f"战损价值：{self._format_isk(value)}\n"
            f"https://zkillboard.com/kill/{killmail_id}/"
        )

    @staticmethod
    def _positive_int(value):
        try:
            result = int(value)
        except (TypeError, ValueError):
            return None
        return result if result > 0 else None

    @staticmethod
    def _number(value) -> float:
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _parse_recent_time(value: str) -> str:
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(dt.timezone(dt.timedelta(hours=8))).strftime(
                "%Y-%m-%d %H:%M UTC+8"
            )
        except ValueError:
            return "未知时间 UTC+8"

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
