from __future__ import annotations

import asyncio
import re

from .catalog import EveCatalog, EveType, normalize_name
from .client import PLEX_TYPE_ID, EsiMarketClient, MarketQuote
from .sde import SdeUpdater


class EveFeature:
    def __init__(
        self,
        catalog: EveCatalog,
        market: EsiMarketClient,
        updater: SdeUpdater,
        search_result_limit: int = 5,
    ):
        self.catalog = catalog
        self.market = market
        self.updater = updater
        self.search_result_limit = min(20, max(1, search_result_limit))
        self._update_lock = asyncio.Lock()

    async def handle(self, message: str, *, is_admin: bool = False, actor: str = "") -> str:
        command = re.sub(r"^/?(?:jita|jt)(?:\s+|$)", "", message.strip(), count=1).strip()
        if not command or command in {"帮助", "help"}:
            return self.help_text()
        if command.startswith("搜索 "):
            return await asyncio.to_thread(self._search, command[3:].strip())
        if command.startswith("别名 "):
            return await self._aliases(command[3:].strip(), is_admin, actor)
        if command.startswith("数据 "):
            return await self._data(command[3:].strip(), is_admin)
        return await self.query(command)

    async def query(self, query: str) -> str:
        item_query = query.strip()
        if re.fullmatch(r".+?\s*(?:\*|×|[xX])\s*\d+\s*", item_query):
            return "当前只查询物品单价，请去掉数量，例如：/jt 毒蜥级"
        if normalize_name(item_query) in {"plex", "伊甸币"}:
            item = EveType(PLEX_TYPE_ID, "PLEX", "伊甸币")
            return await self._quote(item, "global")
        if item_query.isdigit():
            item = await asyncio.to_thread(self.catalog.get_type, int(item_query))
            if item is None:
                status = await asyncio.to_thread(self.catalog.status)
                if not status["count"]:
                    type_id = int(item_query)
                    item = EveType(
                        type_id, "PLEX" if type_id == PLEX_TYPE_ID else f"Type {type_id}", None
                    )
                else:
                    return f"未找到物品 ID {item_query}，或该 ID 不在当前名称库中。"
            if not self._is_tradeable(item):
                return f"物品 {item.display_name}（{item.type_id}）未发布或不可在市场交易。"
            return await self._quote(item, "global" if item.type_id == PLEX_TYPE_ID else "jita")
        alias = await asyncio.to_thread(self.catalog.alias, item_query)
        if alias:
            return await self._quote(alias, "global" if alias.type_id == PLEX_TYPE_ID else "jita")
        asks_for_blueprint = self._asks_for_blueprint(item_query)
        asks_for_skin = self._asks_for_skin(item_query)
        official = await asyncio.to_thread(
            self.catalog.official_exact,
            item_query,
            include_unmarketable=asks_for_blueprint,
        )
        candidates = await asyncio.to_thread(
            self.catalog.search,
            item_query,
            self.search_result_limit + 1,
            include_blueprints=asks_for_blueprint,
            include_skins=asks_for_skin,
        )
        if not candidates:
            status = await asyncio.to_thread(self.catalog.status)
            if not status["count"]:
                return "EVE 名称库尚未初始化，请管理员执行：/jt 数据 更新"
            return f"没有找到“{item_query}”，可尝试输入更完整的中英文名称或物品 ID。"
        if official and len(candidates) == 1 and candidates[0].type_id == official.type_id:
            return await self._quote(
                official, "global" if official.type_id == PLEX_TYPE_ID else "jita"
            )
        return self._candidate_text(item_query, candidates[: self.search_result_limit])

    @staticmethod
    def _asks_for_blueprint(query: str) -> bool:
        normalized = normalize_name(query)
        return "蓝图" in normalized or "blueprint" in normalized

    @staticmethod
    def _asks_for_skin(query: str) -> bool:
        normalized = normalize_name(query)
        return "涂装" in normalized or "skin" in normalized

    @staticmethod
    def _is_tradeable(item: EveType) -> bool:
        # 名称库为空时，显式 ID 使用占位对象并交由 ESI 判断是否存在行情。
        return item.name_en.startswith("Type ") or (
            item.published and item.market_group_id is not None
        )

    async def _quote(self, item: EveType, market: str) -> str:
        quote = await asyncio.to_thread(self.market.quote, item.type_id, market)
        return self._format_quote(item, quote)

    def _search(self, query: str) -> str:
        if not query:
            return "用法：/jt 搜索 <物品名称>"
        candidates = self.catalog.search(
            query,
            self.search_result_limit + 1,
            include_blueprints=self._asks_for_blueprint(query),
            include_skins=self._asks_for_skin(query),
        )
        return (
            self._candidate_text(query, candidates[: self.search_result_limit])
            if candidates
            else f"没有找到“{query}”。"
        )

    async def _aliases(self, command: str, is_admin: bool, actor: str) -> str:
        if command == "列表":
            rows = await asyncio.to_thread(self.catalog.list_aliases)
            return (
                "别名列表为空。"
                if not rows
                else "别名列表：\n"
                + "\n".join(f"• {name} → {item.display_name}" for name, item in rows)
            )
        if not is_admin:
            return "只有 AstrBot 管理员可以修改 EVE 别名。"
        if command.startswith("添加 "):
            match = re.fullmatch(r"添加\s+(\S+)\s+(.+)", command)
            if not match:
                return "用法：/jt 别名 添加 <别名> <目标物品名称>"
            target = await asyncio.to_thread(self.catalog.official_exact, match.group(2))
            if target is None:
                candidates = await asyncio.to_thread(
                    self.catalog.search,
                    match.group(2),
                    2,
                    include_blueprints=self._asks_for_blueprint(match.group(2)),
                    include_skins=self._asks_for_skin(match.group(2)),
                )
                if len(candidates) != 1:
                    return f"无法唯一确定目标物品“{match.group(2)}”。\n" + self._candidate_text(
                        match.group(2), candidates
                    )
                target = candidates[0]
            try:
                await asyncio.to_thread(
                    self.catalog.add_alias, match.group(1), target.type_id, actor
                )
            except ValueError as error:
                return f"添加别名失败：{error}"
            return f"已添加别名：{match.group(1)} → {target.display_name}"
        if command.startswith("删除 "):
            name = command[3:].strip()
            removed = await asyncio.to_thread(self.catalog.remove_alias, name)
            return f"已删除别名：{name}" if removed else f"别名不存在：{name}"
        return "用法：/jt 别名 添加 <别名> <目标物品名称>｜删除 <别名>｜列表"

    async def _data(self, command: str, is_admin: bool) -> str:
        if command == "状态":
            status = await asyncio.to_thread(self.catalog.status)
            return (
                f"EVE 名称库：{status['count']} 个类型\n"
                f"SDE 构建：{status['build'] or '未初始化'}\n"
                f"更新时间：{status['updated_at'] or '-'}"
            )
        if command in {"更新", "强制更新"}:
            if not is_admin:
                return "只有 AstrBot 管理员可以更新 EVE 名称库。"
            if self._update_lock.locked():
                return "EVE 名称库正在更新，请稍后查看状态。"
            async with self._update_lock:
                try:
                    build, count, changed = await asyncio.to_thread(
                        self.updater.update, command == "强制更新"
                    )
                except Exception as error:
                    return f"EVE 名称库更新失败：{error}"
            action = "更新完成" if changed else "已是最新"
            return f"EVE 名称库{action}：SDE {build}，共 {count} 个类型。"
        return "用法：/jt 数据 更新｜强制更新｜状态"

    @staticmethod
    def _candidate_text(query: str, candidates: list[EveType]) -> str:
        if not candidates:
            return f"没有找到“{query}”。"
        lines = [f"“{query}”匹配到以下物品，请使用 /jt <ID> 查询："]
        lines.extend(
            f"{index}. {item.display_name}（{item.type_id}）"
            for index, item in enumerate(candidates, 1)
        )
        return "\n".join(lines)

    @staticmethod
    def _format_quote(item: EveType, quote: MarketQuote) -> str:
        sell = EveFeature._isk(quote.sell_min)
        buy = EveFeature._isk(quote.buy_max)
        middle = (
            EveFeature._isk((quote.sell_min + quote.buy_max) / 2)
            if quote.sell_min is not None and quote.buy_max is not None
            else "暂无报价"
        )
        lines = [
            f"📦 {item.display_name}",
            "",
            f"最低卖价：{sell}",
            f"最高收价：{buy}",
            f"中间价：{middle}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _isk(value: float | None) -> str:
        return "暂无报价" if value is None else f"{value:,.2f} ISK"

    @staticmethod
    def help_text() -> str:
        return (
            "EVE 欧服吉他查价：\n"
            "• /jt 三钛合金（/jita 同义）\n"
            "• /jt 毒蜥级\n"
            "• /jt PLEX\n"
            "• /jt 34\n"
            "• /jt 搜索 乌鸦\n"
            "• /jt 别名 添加 月卡 PLEX\n"
            "• /jt 数据 更新｜状态\n"
            "普通物品查询吉他 4-4；PLEX/伊甸币查询全球 PLEX 市场。"
        )
