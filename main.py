"""AstrBot 插件入口：仅声明命令、组装适配器和转发生命周期。"""

from pathlib import Path

from astrbot.api.event import filter
from astrbot.api.star import Context, Star, StarTools, register

from .plugin.adapters.astrbot.commands import (
    actor_id,
    eve_query_results,
    html_card_result,
    is_admin_event,
    is_group_event,
    message_text,
    platform_name,
    prevent_default_reply,
    query_result,
    stop_event_propagation,
    unified_origin,
)
from .plugin.adapters.astrbot.notifications import AstrBotGroupNotifier
from .plugin.application import PluginApplication
from .plugin.core.config import PluginConfig
from .plugin.core.storage import JsonFileStore
from .plugin.features.rat.client import EVE_BINDING_HINT


@register(
    "yuxuandnf",
    "Sir 丶雨轩",
    "烟雨机器人插件，支持 DNF 金币比例、油价、蛋价和 EVE 查询。",
    "v1.7",
)
class DNF_Plugin(Star):
    """保留历史插件标识及入口类名，兼容已有安装。"""

    def __init__(self, context: Context, config=None) -> None:
        super().__init__(context)
        cfg = PluginConfig(config)
        store = JsonFileStore(
            StarTools.get_data_dir("yuxuandnf"),
            legacy_dir=Path(__file__).resolve().parent,
        )
        self.app = PluginApplication(cfg, store, AstrBotGroupNotifier(context, cfg))

    async def initialize(self) -> None:
        await self.app.runtime.start()

    @filter.command("help")
    async def help(self, event):
        """显示烟雨机器人插件指令帮助。"""
        prevent_default_reply(event)
        stop_event_propagation(event)
        yield await query_result(event, "帮助", self.app.help.query)

    @filter.command("status")
    async def status(self, event):
        """查询 EVE Tranquility 服务器状态和在线人数。"""
        yield await query_result(event, "EVE 状态", self.app.eve_dt.query)

    @filter.command("金币比例")
    async def dnf_gold_ratio(self, event):
        """查询 DNF 金币比例。"""
        yield await query_result(event, "金币比例", self.app.gold.query)

    @filter.command("油价")
    async def oil_price(self, event):
        """查询油价或计算行驶成本：油价 河南 92 8 500。"""
        yield await query_result(event, "油价", self.app.oil.query, message_text(event))

    @filter.command("蛋价")
    async def egg_price(self, event):
        """查询蛋价：蛋价 平舆 / 蛋价 平舆 20260911。"""
        yield await query_result(event, "蛋价", self.app.egg.query, message_text(event))

    @filter.command("rat")
    async def rat(self, event):
        """使用发送者 QQ 查询 RAT 接口。"""
        yield await query_result(
            event, "rat", self.app.rat.query, actor_id(event), error_text=EVE_BINDING_HINT
        )

    @filter.command("info")
    async def info(self, event):
        """使用发送者 QQ 查询绑定的 EVE 用户信息。"""
        yield await query_result(
            event, "info", self.app.info.query, actor_id(event), error_text=EVE_BINDING_HINT
        )

    @filter.command("tr")
    async def translate(self, event):
        """翻译 EVE 中文或英文名称。"""
        prevent_default_reply(event)
        yield await query_result(
            event, "EVE 名称翻译", self.app.translate.query, message_text(event)
        )

    @filter.command("nav")
    async def navigation(self, event):
        """为当前 QQ 绑定的 EVE 角色设置目的地航点。"""
        yield await query_result(
            event,
            "EVE 导航",
            self.app.navigation.query,
            message_text(event),
            actor_id(event),
        )

    @filter.command("where")
    async def where(self, event):
        """按发送者 QQ 搜索已同步的 EVE 资产。"""
        yield await query_result(
            event, "资产位置", self.app.where.query, message_text(event), actor_id(event)
        )

    @filter.command("fleet")
    async def fleet(self, event):
        """使用 QQ 绑定的主角色发送舰队邀请。"""
        yield await query_result(
            event, "舰队邀请", self.app.fleet.query, message_text(event), actor_id(event)
        )

    @filter.command("timer")
    async def timer(self, event):
        """计算指定时长后的 EVE 时间和北京时间。"""
        yield await query_result(event, "timer", self.app.timer.query, message_text(event))

    @filter.command("ship", alias={"舰船"})
    async def ship(self, event):
        """查询 EVE 舰船槽位和加成，并返回图片卡片。"""
        prevent_default_reply(event)
        yield await html_card_result(
            event,
            "舰船资料",
            self.app.ship.query,
            message_text(event),
            html_renderer=self.html_render,
        )

    @filter.command("train")
    async def ship_training(self, event):
        """查询发送者绑定角色驾驶舰船所需的立即训练时间。"""
        prevent_default_reply(event)
        yield await query_result(
            event,
            "舰船训练",
            self.app.ship_training.query,
            message_text(event),
            actor_id(event),
            error_text=EVE_BINDING_HINT,
        )

    @filter.command("kb")
    async def kb(self, event):
        """按角色名查询 zKillboard 战绩。"""
        yield await query_result(event, "KB", self.app.kb.query, message_text(event))

    @filter.command("subkb")
    async def subkb(self, event):
        """在群聊中订阅或取消军团 KB 私聊通知。"""
        yield await query_result(
            event,
            "KB 订阅",
            self.app.kb_watch.toggle,
            actor_id(event),
            is_group=is_group_event(event),
        )

    @filter.command("suballkb")
    async def suballkb(self, event):
        """在 KOOK 频道中订阅或取消联盟 KB 通知。"""
        yield await query_result(
            event,
            "联盟 KB 订阅",
            self.app.kb_watch.toggle_alliance,
            unified_origin(event),
            platform_name=platform_name(event),
            is_group=is_group_event(event),
        )

    @filter.command("jita", alias={"jt"})
    async def eve_market(self, event):
        """查询 EVE Tranquility 吉他市场；jt 为同义命令。"""
        prevent_default_reply(event)
        results = await eve_query_results(
            event,
            self.app.eve.handle_reply,
            message_text(event),
            html_renderer=self.html_render,
            is_admin=is_admin_event(event),
            actor=actor_id(event),
        )
        for result in results:
            yield result

    @filter.command("col")
    async def eve_collection(self, event):
        """按物品和数量查询 EVE 市场单价及最低卖价合计。"""
        prevent_default_reply(event)
        yield await query_result(
            event,
            "EVE 合计",
            self.app.eve.handle_collection,
            message_text(event),
        )

    async def terminate(self) -> None:
        await self.app.runtime.stop()
