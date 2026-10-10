from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from .catalog import EveCatalog, EveType, normalize_name
from .chart import PriceChartRenderer
from .client import PLEX_TYPE_ID, MarketClient, MarketQuote
from .sde import SdeUpdater

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EveReply:
    text: str
    chart_html: str | None = None


class EveFeature:
    def __init__(
        self,
        catalog: EveCatalog,
        market: MarketClient,
        updater: SdeUpdater,
        search_result_limit: int = 5,
        chart_renderer: PriceChartRenderer | None = None,
    ):
        self.catalog = catalog
        self.market = market
        self.updater = updater
        self.search_result_limit = min(20, max(1, search_result_limit))
        self.chart_renderer = chart_renderer
        self._update_lock = asyncio.Lock()
        self._reply_flights: dict[str, asyncio.Task[EveReply]] = {}
        self._reply_flights_lock = asyncio.Lock()

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

    async def handle_collection(self, message: str) -> str:
        command = re.sub(r"^/?col(?:\s+|$)", "", message.strip(), count=1).strip()
        if not command or command in {"帮助", "help"}:
            return self.collection_help_text()
        match = re.fullmatch(r"(.+?)\s+(?:(?:\*|×|[xX])\s*)?(\d+)", command)
        if match is None:
            if re.search(r"\s+(?:(?:\*|×|[xX])\s*)?[+-]?\d+(?:\.\d+)?$", command):
                return "数量必须是 1 至 2,147,483,647 之间的整数"
            return await self._query(command, quantity=1, collection_total=True)
        item_query = match.group(1).strip()
        quantity = int(match.group(2))
        if quantity <= 0 or quantity > 2_147_483_647:
            return "数量必须是 1 至 2,147,483,647 之间的整数"
        return await self._query(
            item_query,
            quantity=quantity,
            include_total=True,
            collection_total=True,
        )

    async def handle_reply(
        self, message: str, *, is_admin: bool = False, actor: str = ""
    ) -> EveReply:
        command = self._item_command(message)
        if command is None:
            return await self._handle_reply_once(message, is_admin=is_admin, actor=actor)
        # Collapse concurrent identical lookups without serialising unrelated items.
        flight_key = normalize_name(command)
        async with self._reply_flights_lock:
            task = self._reply_flights.get(flight_key)
            if task is None:
                task = asyncio.create_task(
                    self._handle_reply_once(message, is_admin=is_admin, actor=actor)
                )
                self._reply_flights[flight_key] = task
        try:
            return await asyncio.shield(task)
        finally:
            if task.done():
                async with self._reply_flights_lock:
                    if self._reply_flights.get(flight_key) is task:
                        self._reply_flights.pop(flight_key, None)

    async def _handle_reply_once(
        self, message: str, *, is_admin: bool = False, actor: str = ""
    ) -> EveReply:
        if self.chart_renderer is None:
            return EveReply(await self.handle(message, is_admin=is_admin, actor=actor))
        command = self._item_command(message)
        if command is None:
            return EveReply(await self.handle(message, is_admin=is_admin, actor=actor))
        resolved = await self._resolve_single(command)
        if resolved is None:
            return EveReply(await self.handle(message, is_admin=is_admin, actor=actor))
        item, market, quantity = resolved
        # Current orders and history are independent upstream requests. Run them together so
        # a first query costs roughly the slower request instead of the sum of both requests.
        # We have already resolved the item above.  Calling ``handle`` here would repeat
        # alias/exact/fuzzy database work before issuing the same quote request.
        text_task = asyncio.create_task(self._quote(item, market, query=command, quantity=quantity))
        try:
            history = await asyncio.to_thread(self.market.history, item.type_id, market, 30)
            text = await text_task
            chart = await asyncio.to_thread(
                self.chart_renderer.render,
                item.type_id,
                self._localized_name(item, self._prefers_chinese(command)),
                history,
                quantity=quantity,
            )
            chart_html = chart.html if chart else None
        except Exception:
            # 历史行情或绘图失败不能影响当前价格回复。
            logger.exception("生成 EVE 价格走势图失败: type_id=%s", item.type_id)
            text = await text_task
            chart_html = None
        return EveReply(text, chart_html)

    @staticmethod
    def _item_command(message: str) -> str | None:
        command = re.sub(r"^/?(?:jita|jt)(?:\s+|$)", "", message.strip(), count=1).strip()
        if (
            not command
            or command in {"帮助", "help"}
            or command.startswith(("搜索 ", "别名 ", "数据 "))
            or re.fullmatch(r".+?\s*(?:\*|×|[xX])\s*\d+\s*", command)
        ):
            return None
        return command

    async def _resolve_single(self, query: str) -> tuple[EveType, str, int] | None:
        normalized = normalize_name(query)
        if normalized in {"plex", "伊甸币"}:
            return EveType(PLEX_TYPE_ID, "PLEX", "伊甸币"), "global", 500
        if query.isdigit():
            item = await asyncio.to_thread(self.catalog.get_type, int(query))
            if item is None or not self._is_tradeable(item):
                return None
            return (
                item,
                "global" if item.type_id == PLEX_TYPE_ID else "jita",
                (500 if item.type_id == PLEX_TYPE_ID else 1),
            )
        alias = await asyncio.to_thread(self.catalog.alias, query)
        if alias:
            return (
                alias,
                "global" if alias.type_id == PLEX_TYPE_ID else "jita",
                (500 if alias.type_id == PLEX_TYPE_ID else 1),
            )
        blueprint = self._asks_for_blueprint(query)
        official = await asyncio.to_thread(
            self.catalog.official_exact, query, include_unmarketable=blueprint
        )
        if official:
            return (
                official,
                "global" if official.type_id == PLEX_TYPE_ID else "jita",
                (500 if official.type_id == PLEX_TYPE_ID else 1),
            )
        candidates = await asyncio.to_thread(
            self.catalog.search,
            query,
            self.search_result_limit + 1,
            include_blueprints=blueprint,
            include_skins=self._asks_for_skin(query),
        )
        if len(candidates) != 1:
            return None
        item = candidates[0]
        return (
            item,
            "global" if item.type_id == PLEX_TYPE_ID else "jita",
            (500 if item.type_id == PLEX_TYPE_ID else 1),
        )

    async def query(self, query: str) -> str:
        return await self._query(query)

    async def _query(
        self,
        query: str,
        *,
        quantity: int | None = None,
        include_total: bool = False,
        collection_total: bool = False,
    ) -> str:
        item_query = query.strip()
        if re.fullmatch(r".+?\s*(?:\*|×|[xX])\s*\d+\s*", item_query):
            return "当前只查询物品单价，请去掉数量，例如：/jt 毒蜥级"
        if normalize_name(item_query) in {"plex", "伊甸币"}:
            item = EveType(PLEX_TYPE_ID, "PLEX", "伊甸币")
            return await self._quote(
                item,
                "global",
                query=item_query,
                quantity=quantity if quantity is not None else 500,
                include_total=include_total,
                total_label="总计价格" if collection_total else None,
            )
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
            return await self._quote(
                item,
                "global" if item.type_id == PLEX_TYPE_ID else "jita",
                query=item_query,
                quantity=(
                    quantity
                    if quantity is not None
                    else (500 if item.type_id == PLEX_TYPE_ID else 1)
                ),
                include_total=include_total,
                total_label="总计价格" if collection_total else None,
            )
        alias = await asyncio.to_thread(self.catalog.alias, item_query)
        if alias:
            return await self._quote(
                alias,
                "global" if alias.type_id == PLEX_TYPE_ID else "jita",
                query=item_query,
                quantity=(
                    quantity
                    if quantity is not None
                    else (500 if alias.type_id == PLEX_TYPE_ID else 1)
                ),
                include_total=include_total,
                total_label="总计价格" if collection_total else None,
            )
        asks_for_blueprint = self._asks_for_blueprint(item_query)
        asks_for_skin = self._asks_for_skin(item_query)
        official = await asyncio.to_thread(
            self.catalog.official_exact,
            item_query,
            include_unmarketable=asks_for_blueprint,
        )
        if official:
            return await self._quote(
                official,
                "global" if official.type_id == PLEX_TYPE_ID else "jita",
                query=item_query,
                quantity=(
                    quantity
                    if quantity is not None
                    else (500 if official.type_id == PLEX_TYPE_ID else 1)
                ),
                include_total=include_total,
                total_label="总计价格" if collection_total else None,
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
        return await self._quotes(
            candidates[: self.search_result_limit],
            item_query,
            quantity=quantity if quantity is not None else 1,
            include_total=include_total,
            collection_total=collection_total,
        )

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
        # 名称库为空时，显式 ID 使用占位对象并交由行情服务判断是否存在报价。
        return item.name_en.startswith("Type ") or (
            item.published and item.market_group_id is not None
        )

    async def _quote(
        self,
        item: EveType,
        market: str,
        *,
        query: str = "",
        quantity: int = 1,
        include_total: bool = False,
        total_label: str | None = None,
    ) -> str:
        quote = await asyncio.to_thread(self.market.quote, item.type_id, market)
        return self._format_quote(
            item,
            quote,
            prefer_chinese=self._prefers_chinese(query),
            quantity=quantity,
            include_total=include_total,
            total_label=total_label,
        )

    async def _quotes(
        self,
        items: list[EveType],
        query: str,
        *,
        quantity: int = 1,
        include_total: bool = False,
        collection_total: bool = False,
    ) -> str:
        """优先批量查询模糊匹配结果，避免逐项等待行情接口。"""
        quote_many = (
            getattr(self.market, "quote_many", None)
            if getattr(self.market, "supports_batch_quotes", False) is True
            else None
        )
        if callable(quote_many) and all(item.type_id != PLEX_TYPE_ID for item in items):
            try:
                quotes = await asyncio.to_thread(
                    quote_many,
                    [item.type_id for item in items],
                    "jita",
                )
                return self._format_quotes(
                    items,
                    query,
                    quotes,
                    quantity=quantity,
                    include_total=include_total,
                    collection_total=collection_total,
                )
            except Exception:
                logger.exception("EVE 批量行情查询失败，降级到逐项查询")
        if collection_total:
            results = await asyncio.gather(
                *(
                    asyncio.to_thread(
                        self.market.quote,
                        item.type_id,
                        "global" if item.type_id == PLEX_TYPE_ID else "jita",
                    )
                    for item in items
                ),
                return_exceptions=True,
            )
            quotes = {
                item.type_id: result
                for item, result in zip(items, results)
                if isinstance(result, MarketQuote)
            }
            return self._format_quotes(
                items,
                query,
                quotes,
                quantity=quantity,
                collection_total=True,
            )
        results = await asyncio.gather(
            *(
                self._quote(
                    item,
                    "global" if item.type_id == PLEX_TYPE_ID else "jita",
                    query=query,
                    quantity=(
                        quantity if include_total else (500 if item.type_id == PLEX_TYPE_ID else 1)
                    ),
                    include_total=include_total,
                )
                for item in items
            ),
            return_exceptions=True,
        )
        sections = []
        for item, result in zip(items, results):
            if isinstance(result, Exception):
                sections.append(
                    f"{self._localized_name(item, self._prefers_chinese(query))}\n"
                    "查询失败：行情接口暂时不可用，请稍后重试"
                )
            else:
                sections.append(result.replace("\n\n", "\n", 1))
        return "\n──────────\n".join(sections)

    def _format_quotes(
        self,
        items: list[EveType],
        query: str,
        quotes: dict[int, MarketQuote],
        *,
        quantity: int = 1,
        include_total: bool = False,
        collection_total: bool = False,
    ) -> str:
        prefer_chinese = self._prefers_chinese(query)
        sections = []
        sell_total = 0.0
        buy_total = 0.0
        middle_total = 0.0
        sell_count = 0
        buy_count = 0
        middle_count = 0
        for item in items:
            quote = quotes.get(item.type_id)
            if quote is None:
                sections.append(f"{self._localized_name(item, prefer_chinese)}\n暂无报价")
            else:
                sections.append(
                    self._format_quote(
                        item,
                        quote,
                        prefer_chinese=prefer_chinese,
                        quantity=quantity,
                        include_total=include_total,
                    ).replace("\n\n", "\n", 1)
                )
                if quote.sell_min is not None:
                    sell_total += quote.sell_min * quantity
                    sell_count += 1
                if quote.buy_max is not None:
                    buy_total += quote.buy_max * quantity
                    buy_count += 1
                if quote.sell_min is not None and quote.buy_max is not None:
                    middle_total += (quote.sell_min + quote.buy_max) / 2 * quantity
                    middle_count += 1
        if collection_total:
            sections.append(
                "总计价格\n"
                f"最低卖价合计（{sell_count} 项）："
                f"{self._isk(sell_total) if sell_count else '暂无报价'}\n"
                f"最高收价合计（{buy_count} 项）："
                f"{self._isk(buy_total) if buy_count else '暂无报价'}\n"
                f"中间价合计（{middle_count} 项）："
                f"{self._isk(middle_total) if middle_count else '暂无报价'}"
            )
        return "\n──────────\n".join(sections)

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

    @classmethod
    def _candidate_text(cls, query: str, candidates: list[EveType]) -> str:
        if not candidates:
            return f"没有找到“{query}”。"
        lines = [f"“{query}”匹配到以下物品，请使用 /jt <ID> 查询："]
        lines.extend(
            f"{index}. {cls._localized_name(item, cls._prefers_chinese(query))}（{item.type_id}）"
            for index, item in enumerate(candidates, 1)
        )
        return "\n".join(lines)

    @staticmethod
    def _prefers_chinese(query: str) -> bool:
        # ID 查询没有语言线索，面向当前中文插件默认使用中文名称。
        return not query or query.isdigit() or bool(re.search(r"[\u3400-\u9fff]", query))

    @staticmethod
    def _localized_name(item: EveType, prefer_chinese: bool) -> str:
        return (item.name_zh or item.name_en) if prefer_chinese else item.name_en

    @staticmethod
    def _format_quote(
        item: EveType,
        quote: MarketQuote,
        *,
        prefer_chinese: bool = True,
        quantity: int = 1,
        include_total: bool = False,
        total_label: str | None = None,
    ) -> str:
        multiplier = 1 if include_total else quantity
        sell = EveFeature._isk(quote.sell_min * multiplier if quote.sell_min is not None else None)
        buy = EveFeature._isk(quote.buy_max * multiplier if quote.buy_max is not None else None)
        middle = (
            EveFeature._isk((quote.sell_min + quote.buy_max) / 2 * multiplier)
            if quote.sell_min is not None and quote.buy_max is not None
            else "暂无报价"
        )
        lines = [
            f"{EveFeature._localized_name(item, prefer_chinese)}"
            f"{f' × {quantity}' if quantity != 1 or include_total else ''}",
            "",
            f"最低卖价：{sell}",
            f"最高收价：{buy}",
            f"中间价：{middle}",
        ]
        if include_total:
            sell_total = EveFeature._isk(
                quote.sell_min * quantity if quote.sell_min is not None else None
            )
            buy_total = EveFeature._isk(
                quote.buy_max * quantity if quote.buy_max is not None else None
            )
            middle_total = (
                EveFeature._isk((quote.sell_min + quote.buy_max) / 2 * quantity)
                if quote.sell_min is not None and quote.buy_max is not None
                else "暂无报价"
            )
            lines.extend(
                (
                    f"最低卖价合计：{sell_total}",
                    f"最高收价合计：{buy_total}",
                    f"中间价合计：{middle_total}",
                )
            )
        elif total_label:
            sell_total = EveFeature._isk(
                quote.sell_min * quantity if quote.sell_min is not None else None
            )
            buy_total = EveFeature._isk(
                quote.buy_max * quantity if quote.buy_max is not None else None
            )
            middle_total = (
                EveFeature._isk((quote.sell_min + quote.buy_max) / 2 * quantity)
                if quote.sell_min is not None and quote.buy_max is not None
                else "暂无报价"
            )
            lines.extend(
                (
                    total_label,
                    f"最低卖价合计：{sell_total}",
                    f"最高收价合计：{buy_total}",
                    f"中间价合计：{middle_total}",
                )
            )
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

    @staticmethod
    def collection_help_text() -> str:
        return (
            "EVE 数量合计查价\n"
            "用法：/col <物品名称或 ID> [数量]\n"
            "• /col 中级水晶\n"
            "• /col 毒蜥级 10\n"
            "• /col Tritanium * 1000\n"
            "• /col 34 × 1000\n"
            "多项结果会将各项最低卖价相加；指定数量时按最低卖价 × 数量计算。"
        )
