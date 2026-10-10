"""使用最小框架替身验证入口，不需要安装或启动 AstrBot。"""

import importlib
import importlib.util
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from plugin.adapters.astrbot.notifications import AstrBotGroupNotifier
from plugin.core.config import PluginConfig


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_notifier_resolves_configured_platform(self):
        client = SimpleNamespace(send_group_msg=AsyncMock(), send_private_msg=AsyncMock())
        platform = SimpleNamespace(
            meta=lambda: SimpleNamespace(name="aiocqhttp"), get_client=lambda: client
        )
        context = SimpleNamespace(
            platform_manager=SimpleNamespace(get_insts=lambda: [platform]),
            send_message=AsyncMock(return_value=True),
        )
        notifier = AstrBotGroupNotifier(context, PluginConfig())
        self.assertTrue(await notifier.send_group(123, "测试"))
        client.send_group_msg.assert_awaited_once_with(group_id=123, message="测试")
        self.assertTrue(await notifier.send_private(456, "私聊测试"))
        client.send_private_msg.assert_awaited_once_with(user_id=456, message="私聊测试")

        class MessageChain:
            def message(self, text):
                self.text = text
                return self

        event_module = ModuleType("astrbot.api.event")
        event_module.MessageChain = MessageChain
        with patch.dict(sys.modules, {"astrbot.api.event": event_module}):
            self.assertTrue(await notifier.send_session("kook:GroupMessage:channel-1", "KB"))
        chain = context.send_message.await_args.args[1]
        context.send_message.assert_awaited_once_with("kook:GroupMessage:channel-1", chain)
        self.assertEqual(chain.text, "KB")

        class CardMessageChain:
            def __init__(self):
                self.chain = []

        event_module.MessageChain = CardMessageChain
        api_module = ModuleType("astrbot.api")
        api_module.message_components = SimpleNamespace(Json=lambda data: ("json", data))
        with patch.dict(
            sys.modules,
            {"astrbot.api": api_module, "astrbot.api.event": event_module},
        ):
            self.assertTrue(
                await notifier.send_session_card("kook:GroupMessage:channel-1", {"type": "card"})
            )
        card_chain = context.send_message.await_args.args[1]
        self.assertEqual(card_chain.chain, [("json", {"type": "card"})])
        missing = AstrBotGroupNotifier(context, PluginConfig({"platform": {"name": "missing"}}))
        self.assertFalse(await missing.send_group(123, "测试"))

    async def test_entrypoint_commands_and_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            modules = {
                name: ModuleType(name)
                for name in (
                    "astrbot",
                    "astrbot.api",
                    "astrbot.api.event",
                    "astrbot.api.star",
                    "astrbot.api.message_components",
                )
            }
            modules["astrbot.api"].logger = logging.getLogger("test.astrbot")
            commands = []

            def command(name, **kwargs):
                commands.append(name)
                return lambda function: function

            def regex(pattern):
                commands.append(pattern)
                return lambda function: function

            class Star:
                def __init__(self, context):
                    self.context = context

                async def html_render(self, template, data, return_url=True, options=None):
                    return "https://example.test/chart.png"

            modules["astrbot.api.event"].filter = SimpleNamespace(command=command, regex=regex)
            modules["astrbot.api.message_components"].Plain = lambda text: ("text", text)
            modules["astrbot.api.message_components"].Image = SimpleNamespace(
                fromFileSystem=lambda path: ("image-file", path),
                fromURL=lambda url: ("image-url", url),
            )
            modules["astrbot.api.message_components"].Json = lambda data: ("json", data)
            star_module = modules["astrbot.api.star"]
            star_module.Context = object
            star_module.Star = Star
            star_module.StarTools = SimpleNamespace(get_data_dir=lambda name: Path(directory))
            star_module.register = lambda *args: lambda cls: cls
            root = Path(__file__).parents[1]
            package_name = "_test_plugin_entry"
            spec = importlib.util.spec_from_file_location(
                package_name, root / "__init__.py", submodule_search_locations=[str(root)]
            )
            package = importlib.util.module_from_spec(spec)
            modules[package_name] = package
            try:
                with patch.dict(sys.modules, modules):
                    module = importlib.import_module(f"{package_name}.main")
                    plugin = module.DNF_Plugin(
                        SimpleNamespace(),
                        {
                            name: {"monitor_enabled": False}
                            for name in ("gold", "oil", "egg", "eve_dt", "kb_watch")
                        },
                    )
                    self.assertEqual(
                        commands,
                        [
                            "help",
                            "status",
                            "金币比例",
                            "油价",
                            "蛋价",
                            "rat",
                            "info",
                            "tr",
                            "timer",
                            "ship",
                            "train",
                            "kb",
                            "subkb",
                            "suballkb",
                            "jita",
                            "col",
                        ],
                    )
                    await plugin.initialize()
                    await plugin.initialize()
                    event = SimpleNamespace(
                        message_str="/help",
                        plain_result=lambda text: text,
                        should_call_llm=lambda value: setattr(event, "call_llm", value),
                        stop_event=Mock(),
                    )
                    self.assertEqual(
                        [item async for item in plugin.help(event)],
                        [plugin.app.help.TEXT],
                    )
                    self.assertTrue(event.call_llm)
                    event.stop_event.assert_called_once_with()
                    plugin.app.eve_dt.query = AsyncMock(return_value="EVE服务器状态：已开服")
                    event = SimpleNamespace(message_str="/status", plain_result=lambda text: text)
                    self.assertEqual(
                        [item async for item in plugin.status(event)],
                        ["EVE服务器状态：已开服"],
                    )
                    plugin.app.eve_dt.query.assert_awaited_once_with()
                    for method, feature in (
                        (plugin.dnf_gold_ratio, plugin.app.gold),
                        (plugin.oil_price, plugin.app.oil),
                        (plugin.egg_price, plugin.app.egg),
                    ):
                        feature.query = AsyncMock(return_value="查询结果")
                        event = SimpleNamespace(
                            message_str="油价 河南", plain_result=lambda text: text
                        )
                        self.assertEqual([item async for item in method(event)], ["查询结果"])
                    plugin.app.gold.query.side_effect = RuntimeError("private details")
                    with self.assertLogs("test.astrbot", level="ERROR"):
                        result = [item async for item in plugin.dnf_gold_ratio(event)]
                    self.assertEqual(result, ["金币比例查询出现异常，请稍后重试"])
                    plugin.app.rat.query = AsyncMock(return_value="RAT 查询结果")
                    event.sender = SimpleNamespace(user_id="123456")
                    self.assertEqual([item async for item in plugin.rat(event)], ["RAT 查询结果"])
                    plugin.app.rat.query.assert_awaited_once_with("123456")
                    plugin.app.rat.query.side_effect = RuntimeError("upstream unavailable")
                    with self.assertLogs("test.astrbot", level="ERROR"):
                        result = [item async for item in plugin.rat(event)]
                    self.assertEqual(
                        result, ["没有找到角色。请先注册eve.oofo.cc 绑定角色和绑定QQ后使用。"]
                    )
                    plugin.app.info.query = AsyncMock(return_value="用户信息")
                    self.assertEqual([item async for item in plugin.info(event)], ["用户信息"])
                    plugin.app.info.query.assert_awaited_once_with("123456")
                    plugin.app.info.query.side_effect = RuntimeError("upstream unavailable")
                    with self.assertLogs("test.astrbot", level="ERROR"):
                        result = [item async for item in plugin.info(event)]
                    self.assertEqual(
                        result, ["没有找到角色。请先注册eve.oofo.cc 绑定角色和绑定QQ后使用。"]
                    )
                    plugin.app.timer.query = AsyncMock(return_value="时间结果")
                    event.message_str = "/timer 2.2.5"
                    self.assertEqual([item async for item in plugin.timer(event)], ["时间结果"])
                    plugin.app.timer.query.assert_awaited_once_with("/timer 2.2.5")
                    plugin.app.ship.query = AsyncMock(
                        return_value=SimpleNamespace(
                            text="乌鸦级舰船资料", html="<html>ship</html>"
                        )
                    )
                    plugin.html_render = AsyncMock(return_value="/tmp/ship.png")
                    event.message_str = "/ship 乌鸦级"
                    event.chain_result = lambda chain: chain
                    self.assertEqual(
                        [item async for item in plugin.ship(event)],
                        [[("image-file", "/tmp/ship.png")]],
                    )
                    plugin.app.ship.query.assert_awaited_once_with("/ship 乌鸦级")
                    plugin.app.ship_training.query = AsyncMock(return_value="乌鸦级舰船训练")
                    event.message_str = "/train 乌鸦级"
                    self.assertEqual(
                        [item async for item in plugin.ship_training(event)],
                        ["乌鸦级舰船训练"],
                    )
                    plugin.app.ship_training.query.assert_awaited_once_with(
                        "/train 乌鸦级", "123456"
                    )
                    plugin.app.kb.query = AsyncMock(return_value="KB 查询结果")
                    event.message_str = "/kb Yuxan Axiom"
                    self.assertEqual([item async for item in plugin.kb(event)], ["KB 查询结果"])
                    plugin.app.kb.query.assert_awaited_once_with("/kb Yuxan Axiom")
                    plugin.app.kb_watch.toggle = AsyncMock(return_value="订阅成功")
                    event.message_str = "/subkb"
                    event.get_group_id = lambda: "123456"
                    self.assertEqual([item async for item in plugin.subkb(event)], ["订阅成功"])
                    plugin.app.kb_watch.toggle.assert_awaited_once_with("123456", is_group=True)
                    plugin.app.kb_watch.toggle_alliance = AsyncMock(return_value="联盟订阅成功")
                    event.message_str = "/suballkb"
                    event.get_platform_name = lambda: "kook"
                    event.unified_msg_origin = "kook:GroupMessage:channel-1"
                    self.assertEqual(
                        [item async for item in plugin.suballkb(event)], ["联盟订阅成功"]
                    )
                    plugin.app.kb_watch.toggle_alliance.assert_awaited_once_with(
                        "kook:GroupMessage:channel-1",
                        platform_name="kook",
                        is_group=True,
                    )
                    plugin.app.eve.handle_reply = AsyncMock(
                        return_value=SimpleNamespace(text="EVE 查询结果", chart_html=None)
                    )
                    event.message_str = "/jt PLEX * 500"
                    event.role = "admin"
                    event.sender = SimpleNamespace(user_id="42")
                    event.image_result = lambda path: f"IMAGE:{path}"
                    self.assertEqual(
                        [item async for item in plugin.eve_market(event)], ["EVE 查询结果"]
                    )
                    self.assertTrue(event.call_llm)
                    plugin.app.eve.handle_reply.assert_awaited_once_with(
                        "/jt PLEX * 500", is_admin=True, actor="42"
                    )
                    plugin.app.eve.handle_collection = AsyncMock(return_value="EVE 合计结果")
                    event.message_str = "/col PLEX 500"
                    self.assertEqual(
                        [item async for item in plugin.eve_collection(event)],
                        ["EVE 合计结果"],
                    )
                    plugin.app.eve.handle_collection.assert_awaited_once_with("/col PLEX 500")
                    plugin.app.eve.handle_reply = AsyncMock(
                        return_value=SimpleNamespace(
                            text="EVE 查询结果", chart_html="<html>chart</html>"
                        )
                    )
                    plugin.html_render = AsyncMock(return_value="https://example.test/chart.png")
                    event.chain_result = lambda chain: chain
                    expected_chart_reply = [
                        [("text", "EVE 查询结果"), ("image-url", "https://example.test/chart.png")]
                    ]
                    self.assertEqual(
                        [item async for item in plugin.eve_market(event)],
                        expected_chart_reply,
                    )
                    self.assertEqual(
                        [item async for item in plugin.eve_market(event)], expected_chart_reply
                    )
                    plugin.html_render.assert_awaited_once()
                    await plugin.terminate()
                    await plugin.terminate()
            finally:
                for name in list(sys.modules):
                    if name.startswith(package_name + "."):
                        sys.modules.pop(name, None)
