"""AstrBot 插件入口：仅声明命令、组装适配器和转发生命周期。"""

from pathlib import Path

from astrbot.api.event import filter
from astrbot.api.star import Context, Star, StarTools, register

from .plugin.adapters.astrbot.commands import actor_id, is_admin_event, message_text, query_result
from .plugin.adapters.astrbot.notifications import AstrBotGroupNotifier
from .plugin.application import PluginApplication
from .plugin.core.config import PluginConfig
from .plugin.core.storage import JsonFileStore


@register(
    "yuxuandnf",
    "Sir 丶雨轩",
    "雨轩查询插件，支持 DNF 金币比例、油价、蛋价和 EVE 吉他市场查询。",
    "v1.6",
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

    @filter.command("jita", alias={"jt"})
    async def eve_market(self, event):
        """查询 EVE Tranquility 吉他市场；jt 为同义命令。"""
        yield await query_result(
            event,
            "EVE 市场",
            self.app.eve.handle,
            message_text(event),
            is_admin=is_admin_event(event),
            actor=actor_id(event),
        )

    async def terminate(self) -> None:
        await self.app.runtime.stop()
