"""AstrBot 插件入口：仅声明命令、组装适配器和转发生命周期。"""

from pathlib import Path

from astrbot.api.event import filter
from astrbot.api.star import Context, Star, StarTools, register

from .plugin.adapters.astrbot.commands import (
    actor_id,
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
    "v1.9",
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
        self.app.kb_watch.set_html_renderer(self.html_render)

    async def initialize(self) -> None:
        await self.app.runtime.start()

    @filter.command("add")
    async def qa_add(self, event):
        """添加或更新自定义问答：/add .xx 解答内容。"""
        prevent_default_reply(event)
        stop_event_propagation(event)
        yield await query_result(event, "问答保存", self.app.qa.add, message_text(event))

    @filter.regex(r"^\s*\.")
    async def qa_answer(self, event):
        """精确匹配已保存的问题，未命中时不干预其他消息。"""
        key = (unified_origin(event), actor_id(event))
        if key in self.app.fitting.sessions or key in self.app.fitting.pending:
            return
        answer = self.app.qa.answer(message_text(event))
        if answer is not None:
            prevent_default_reply(event)
            stop_event_propagation(event)
            yield event.plain_result(answer)

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

    @filter.command("subrat")
    async def subrat(self, event):
        """切换每日 23:50 的 RAT 私聊订阅。"""
        yield await query_result(
            event, "RAT 订阅", self.app.rat_subscription.toggle, actor_id(event)
        )

    @filter.command("info")
    async def info(self, event):
        """使用发送者 QQ 查询绑定的 EVE 用户信息。"""
        yield await query_result(
            event, "info", self.app.info.query, actor_id(event), error_text=EVE_BINDING_HINT
        )

    @filter.command("fitt")
    async def fitting(self, event):
        """仅在 QQ 私聊中分步导入 EVE 配置。"""
        prevent_default_reply(event)
        stop_event_propagation(event)
        text = await self.app.fitting.handle(
            unified_origin(event),
            actor_id(event),
            message_text(event),
            is_private=(
                getattr(event.get_message_type(), "name", "") == "FRIEND_MESSAGE"
                and platform_name(event) == "aiocqhttp"
            ),
            start=True,
        )
        yield event.plain_result(text)

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE, priority=100)
    async def fitting_input(self, event):
        """优先接收进行中的私聊输入，防止被默认聊天消耗。"""
        text = message_text(event)
        if text in {"/fitt", "fitt"} or platform_name(event) != "aiocqhttp":
            return
        # 在请求前标记事件，避免导入期间被其他插件或默认 LLM 处理。
        key = (unified_origin(event), actor_id(event))
        active = key in self.app.fitting.sessions or key in self.app.fitting.pending
        if active and (not text.startswith("/") or text == "/cancel"):
            prevent_default_reply(event)
            stop_event_propagation(event)
        reply = await self.app.fitting.handle(
            *key,
            text,
            is_private=True,
        )
        if reply is not None:
            prevent_default_reply(event)
            stop_event_propagation(event)
            yield event.plain_result(reply)

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

    @filter.command("navrs")
    async def navigation_security_agents(self, event):
        """为绑定的全部角色或指定角色设置安全代理。"""
        yield await query_result(
            event,
            "EVE 安全代理",
            self.app.navigation.security_agents,
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
        """按角色、军团或联盟名称查询 zKillboard 战绩。"""
        yield await query_result(event, "KB", self.app.kb.query, message_text(event))

    @filter.command("kbinfo")
    async def kb_info(self, event):
        """按角色名生成公开战力报告图片。"""
        prevent_default_reply(event)
        yield event.plain_result("正在查询角色战力数据，请稍候……")
        yield await html_card_result(
            event,
            "KB 角色战力",
            self.app.kb.query_info,
            message_text(event),
            html_renderer=self.html_render,
        )

    @filter.command("kbk")
    async def kb_kills(self, event):
        """按角色名获取最近一次击杀并渲染战报图片。"""
        prevent_default_reply(event)
        yield event.plain_result("正在查询击毁数据，请稍候……")
        yield await html_card_result(
            event,
            "KB 最近击杀",
            self.app.kb.query_recent,
            message_text(event),
            "kills",
            html_renderer=self.html_render,
        )

    @filter.command("kbl")
    async def kb_losses(self, event):
        """按角色名获取最近一次损失并渲染战报图片。"""
        prevent_default_reply(event)
        yield event.plain_result("正在查询损失数据，请稍候……")
        yield await html_card_result(
            event,
            "KB 最近损失",
            self.app.kb.query_recent,
            message_text(event),
            "losses",
            html_renderer=self.html_render,
        )

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
        yield await query_result(
            event,
            "EVE 市场",
            self.app.eve.handle,
            message_text(event),
            is_admin=is_admin_event(event),
            actor=actor_id(event),
        )

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
