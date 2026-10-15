import asyncio
import datetime as dt
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from plugin.application import PluginApplication
from plugin.core.config import PluginConfig
from plugin.core.storage import JsonFileStore
from plugin.features.egg.client import parse_egg_args
from plugin.features.eve.catalog import EveType
from plugin.features.eve_dt.client import EveServerStatus, EveStatusClient
from plugin.features.eve_dt.service import EveDowntimeFeature
from plugin.features.gold.service import GoldFeature
from plugin.features.help.service import HelpFeature
from plugin.features.info.client import InfoClient
from plugin.features.info.service import InfoFeature
from plugin.features.kb.client import KbClient, KbReport
from plugin.features.kb.service import KbFeature
from plugin.features.kb_watch.client import ZkillLiveClient
from plugin.features.oil.client import calculate_oil_cost, has_oil_price_changed
from plugin.features.rat.client import RatClient
from plugin.features.rat.service import RatFeature
from plugin.features.timer.service import TimerFeature


class FeatureTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = JsonFileStore(self.temp.name)
        self.notifier = AsyncMock()
        self.notifier.send_group.return_value = True
        self.app = PluginApplication(PluginConfig(), self.store, self.notifier)
        self.oil_data = {"name": "河南", "p92": "7.5", "date": "2026-09-11"}

    async def test_oil_query_and_cost(self):
        with patch("plugin.features.oil.service.fetch_oil_data", return_value=self.oil_data):
            self.assertIn("河南", await self.app.oil.query("/油价 河南"))
            self.assertIn("总成本：60.00元", await self.app.oil.query("油价 河南 92 8"))
            self.assertIn("总成本：300.00元", await self.app.oil.query("油价 河南 92 8 500"))

    def test_eve_runtime_enables_chart_rendering(self):
        self.assertIsNotNone(self.app.eve.chart_renderer)

    async def test_oil_invalid_arguments_do_not_call_network(self):
        with patch("plugin.features.oil.service.fetch_oil_data") as fetch:
            for command in (
                "油价",
                "油价 河南 92 8 0",
                "油价 河南 92 1..2",
                "油价 河南 92 8 extra",
                "油价 河南 92 -8",
                "油价 河南 92 0",
            ):
                with self.subTest(command=command):
                    self.assertIn("❌", await self.app.oil.query(command))
            fetch.assert_not_called()

    async def test_oil_missing_data(self):
        with patch("plugin.features.oil.service.fetch_oil_data", return_value=None):
            self.assertIn("查询失败", await self.app.oil.query("油价 河南"))
            self.assertIn("无法获取", await self.app.oil.query("油价 河南 92 8"))

    async def test_oil_failed_delivery_does_not_advance_snapshot(self):
        for result in (False, RuntimeError("disconnected")):
            self.notifier.send_group.side_effect = result if isinstance(result, Exception) else None
            self.notifier.send_group.return_value = False
            with patch("plugin.features.oil.service.fetch_oil_data", return_value=self.oil_data):
                if isinstance(result, Exception):
                    with self.assertRaises(RuntimeError):
                        await self.app.oil._check_and_send_changes()
                else:
                    await self.app.oil._check_and_send_changes()
            self.assertEqual(self.app.oil.last_oil_data, {})
            self.assertEqual(self.store.load("last_oil_data.json", {}), {})

    async def test_oil_success_persists_and_deduplicates(self):
        with patch("plugin.features.oil.service.fetch_oil_data", return_value=self.oil_data):
            await self.app.oil._check_and_send_changes()
            await self.app.oil._check_and_send_changes()
        self.notifier.send_group.assert_awaited_once()
        self.assertEqual(self.store.load("last_oil_data.json", {}), {"河南": self.oil_data})

    async def test_oil_persistence_failure_does_not_advance_memory(self):
        with (
            patch("plugin.features.oil.service.fetch_oil_data", return_value=self.oil_data),
            patch.object(self.store, "save", side_effect=OSError("disk error")),
        ):
            with self.assertRaises(OSError):
                await self.app.oil._check_and_send_changes()
        self.assertEqual(self.app.oil.last_oil_data, {})

    async def test_gold_query(self):
        with patch(
            "plugin.features.gold.service.DnfGoldRatioFetcher.fetch_gold_ratio_text",
            return_value="均价：1元=70.0000万金币",
        ):
            self.assertEqual(await self.app.gold.query(), "均价：1元=70.0000万金币")

    async def test_gold_threshold_and_restart_state(self):
        await self.app.gold._maybe_send_notice(70)
        await self.app.gold._maybe_send_notice(71)
        await self.app.gold._maybe_send_notice(72)
        self.assertEqual(self.notifier.send_group.await_count, 2)
        reloaded = GoldFeature(PluginConfig(), self.store, self.notifier)
        self.assertEqual(reloaded.last_sent_avg_ratio, 72)
        await reloaded._maybe_send_notice(73)
        self.assertEqual(self.notifier.send_group.await_count, 2)

    async def test_gold_no_platform_does_not_advance_state(self):
        self.notifier.send_group.return_value = False
        await self.app.gold._maybe_send_notice(70)
        self.assertIsNone(self.app.gold.last_sent_avg_ratio)
        self.assertEqual(self.store.load("last_sent_avg_ratio.json", {}), {})

    async def test_gold_monitor_runs_one_tick(self):
        with (
            patch(
                "plugin.features.gold.service.DnfGoldRatioFetcher.fetch_gold_ratio_text",
                return_value="均价：1元=70.0000万金币",
            ),
            patch("plugin.features.gold.service.asyncio.sleep", side_effect=asyncio.CancelledError),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await self.app.gold.run()
        self.assertEqual(self.app.gold.last_avg_ratio, 70)
        self.notifier.send_group.assert_awaited_once()

    async def test_gold_invalid_ratio_is_ignored(self):
        for text in ("失败", "均价：1元=0.0000万金币", "均价：1元=1..2万金币"):
            self.assertIsNone(self.app.gold._parse_avg_ratio(text))

    async def test_egg_query(self):
        with patch(
            "plugin.features.egg.service.format_egg_prices", return_value="蛋价结果"
        ) as query:
            self.assertEqual(await self.app.egg.query("/蛋价 平舆 20260911"), "蛋价结果")
            query.assert_called_once_with("平舆", "20260911", 10)

    async def test_egg_daily_notice_uses_given_date_and_persists(self):
        with patch(
            "plugin.features.egg.service.fetch_egg_prices", return_value=[{"price": 3.5}]
        ) as fetch:
            await self.app.egg._send_daily_notice("2026-09-10")
            fetch.assert_called_once_with("平舆", "20260910")
        self.assertEqual(self.app.egg.last_egg_sent_date, "2026-09-10")
        self.assertEqual(
            self.store.load("last_egg_sent_date.json", {}), {"last_egg_sent_date": "2026-09-10"}
        )

    async def test_egg_empty_or_unsent_does_not_commit(self):
        with patch("plugin.features.egg.service.fetch_egg_prices", return_value=[]):
            await self.app.egg._send_daily_notice("2026-09-11")
        self.notifier.send_group.assert_not_awaited()
        self.notifier.send_group.return_value = False
        with patch("plugin.features.egg.service.fetch_egg_prices", return_value=[{"price": 3.5}]):
            await self.app.egg._send_daily_notice("2026-09-11")
        self.assertIsNone(self.app.egg.last_egg_sent_date)

    async def test_rat_uses_sender_qq_and_returns_api_response(self):
        client = RatClient("https://example.test/rat")
        feature = RatFeature(client)
        with patch.object(client, "query", return_value="接口结果") as query:
            self.assertEqual(await feature.query("123456"), "接口结果")
        query.assert_called_once_with("123456")

    async def test_rat_rejects_invalid_qq_without_calling_api(self):
        client = RatClient("https://example.test/rat")
        feature = RatFeature(client)
        with patch.object(client, "query") as query:
            self.assertIn("无法获取", await feature.query("not-a-qq"))
        query.assert_not_called()

    def test_rat_client_formats_success_and_missing_binding(self):
        client = RatClient()
        response = Mock()
        for payload, expected in (
            ({"code": 0, "message": "ok", "data": {"message": "今日报告"}}, "今日报告"),
            (
                {"code": 46104, "message": "没有找到该QQ号的EVE绑定信息"},
                "没有找到角色。请先注册eve.oofo.cc 绑定角色和绑定QQ后使用。",
            ),
        ):
            with self.subTest(payload=payload):
                response.json = lambda payload=payload: payload
                self.assertEqual(client._format_response(response), expected)

    def test_rat_client_places_qq_in_url(self):
        client = RatClient()
        response = Mock()
        response.json = lambda: {"code": 0, "data": {"message": "查询成功"}}
        with patch("plugin.features.rat.client.requests.get", return_value=response) as get:
            self.assertEqual(client.query("1718018032"), "查询成功")
        get.assert_called_once_with(
            "https://admin-api.oofo.cc/game/eve/public/users/by-qq/1718018032/ratting-report",
            timeout=10,
        )

    async def test_info_uses_sender_qq(self):
        client = InfoClient()
        feature = InfoFeature(client)
        with patch.object(client, "query", return_value="用户信息") as query:
            self.assertEqual(await feature.query("1718018032"), "用户信息")
        query.assert_called_once_with("1718018032")

    def test_info_client_places_qq_in_url(self):
        client = InfoClient()
        response = Mock()
        response.json = lambda: {"code": 0, "data": {"nickname": "烟雨江南"}}
        with patch("plugin.features.rat.client.requests.get", return_value=response) as get:
            self.assertIn("烟雨江南", client.query("1718018032"))
        get.assert_called_once_with(
            "https://admin-api.oofo.cc/game/eve/public/users/by-qq/1718018032/info",
            timeout=10,
        )

    def test_eve_status_client_parses_public_status(self):
        response = Mock()
        response.json.return_value = {
            "start_time": "2026-10-09T11:06:00Z",
            "players": 12345,
            "server_version": "1234567",
            "vip": False,
        }
        response.raise_for_status.return_value = None
        client = EveStatusClient(timeout=7, user_agent="test-agent")
        with patch("plugin.features.eve_dt.client.requests.get", return_value=response) as get:
            status = client.status()
        self.assertEqual(status.players, 12345)
        self.assertFalse(status.vip)
        self.assertEqual(status.start_time, dt.datetime(2026, 10, 9, 11, 6, tzinfo=dt.timezone.utc))
        get.assert_called_once_with(
            "https://esi.evetech.net/latest/status/",
            params={"datasource": "tranquility"},
            headers={"User-Agent": "test-agent", "Accept-Encoding": "gzip"},
            timeout=7,
        )

    async def test_eve_dt_warns_then_notifies_online_once(self):
        client = Mock()
        client.status.return_value = EveServerStatus(
            start_time=dt.datetime(2026, 10, 9, 11, 6, tzinfo=dt.timezone.utc),
            players=12345,
            vip=False,
        )
        feature = EveDowntimeFeature(
            PluginConfig({"eve_dt": {"notify_group_id": 987654321}}),
            self.store,
            self.notifier,
            client,
        )
        beijing = dt.timezone(dt.timedelta(hours=8))

        sleep_until_dt = await feature._tick(dt.datetime(2026, 10, 9, 18, 55, tzinfo=beijing))
        self.assertEqual(sleep_until_dt, 300)
        self.notifier.send_group.assert_awaited_once_with(987654321, "5分钟后游戏DT。")

        self.notifier.send_group.reset_mock()
        await feature._tick(dt.datetime(2026, 10, 9, 19, 0, tzinfo=beijing))
        self.notifier.send_group.assert_awaited_once_with(987654321, "游戏已经开服！！！")
        self.assertEqual(feature.state["online_sent_date"], "2026-10-09")

        self.notifier.send_group.reset_mock()
        await feature._tick(dt.datetime(2026, 10, 9, 19, 1, tzinfo=beijing))
        self.notifier.send_group.assert_not_awaited()
        client.status.assert_called_once_with()

    async def test_eve_dt_retries_stale_status_in_30_seconds(self):
        client = Mock()
        client.status.return_value = EveServerStatus(
            start_time=dt.datetime(2026, 10, 8, 11, 5, tzinfo=dt.timezone.utc),
            players=20000,
            vip=False,
        )
        feature = EveDowntimeFeature(PluginConfig(), self.store, self.notifier, client)
        feature._update_state(active_date="2026-10-09")
        beijing = dt.timezone(dt.timedelta(hours=8))

        sleep_seconds = await feature._tick(dt.datetime(2026, 10, 9, 19, 0, tzinfo=beijing))
        self.assertEqual(sleep_seconds, 30)
        self.notifier.send_group.assert_not_awaited()
        self.assertNotIn("online_sent_date", feature.state)

    async def test_eve_status_query_formats_online_maintenance_and_vip(self):
        client = Mock()
        feature = EveDowntimeFeature(PluginConfig(), self.store, self.notifier, client)
        start_time = dt.datetime(2026, 10, 9, 11, 6, tzinfo=dt.timezone.utc)
        for status, expected in (
            (EveServerStatus(start_time, 23456, False), "已开服\n当前在线：23,456 人"),
            (EveServerStatus(start_time, 0, False), "维护中\n当前在线：0 人"),
            (EveServerStatus(start_time, 12, True), "维护中（VIP模式）\n当前在线：12 人"),
        ):
            with self.subTest(status=status):
                client.status.return_value = status
                self.assertIn(expected, await feature.query())

    async def test_kb_query_formats_compact_report(self):
        client = Mock()
        client.query.return_value = KbReport(
            character_id=2124698588,
            character_name="Yuxan Axiom",
            corporation_name="Example Corporation",
            alliance_name="Example Alliance",
            security_status=1.8,
            danger_ratio=72,
            gang_ratio=84,
            ships_destroyed=1284,
            ships_lost=96,
            isk_destroyed=428_670_000_000,
            isk_lost=12_430_000_000,
            solo_kills=37,
            solo_losses=8,
        )
        result = await KbFeature(client).query("/kb Yuxan Axiom")
        self.assertEqual(
            result,
            "【KB 查询】Yuxan Axiom\n"
            "军团：Example Corporation\n"
            "联盟：Example Alliance\n"
            "安全等级：1.80\n"
            "威胁度：72%｜团战率：84%\n"
            "击杀：1,284 艘｜428.67 B ISK\n"
            "损失：96 艘｜12.43 B ISK\n"
            "单杀：37｜单独损失：8\n"
            "ISK 击损比：34.49｜舰船击损比：13.38\n"
            "详情：https://zkillboard.com/character/2124698588/",
        )
        self.assertNotIn("\n\n", result)
        client.query.assert_called_once_with("Yuxan Axiom")

    async def test_kb_query_handles_usage_not_found_and_no_activity(self):
        client = Mock()
        feature = KbFeature(client)
        self.assertIn("用法", await feature.query("/kb"))
        client.query.assert_not_called()

        client.query.return_value = None
        self.assertIn("未找到角色", await feature.query("/kb Missing Pilot"))

        client.query.return_value = KbReport(
            character_id=42,
            character_name="Quiet Pilot",
            corporation_name=None,
            alliance_name=None,
            security_status=None,
            danger_ratio=0,
            gang_ratio=0,
            ships_destroyed=0,
            ships_lost=0,
            isk_destroyed=0,
            isk_lost=0,
            solo_kills=0,
            solo_losses=0,
        )
        self.assertIn("暂无公开", await feature.query("kb Quiet Pilot"))

    async def test_kb_watch_toggle_persists_subscription(self):
        feature = self.app.kb_watch
        self.assertEqual(feature.subscribers, [1718018032])
        self.assertIn("取消", await feature.toggle("1718018032", is_group=True))
        self.assertEqual(feature.subscribers, [])
        self.assertIn("推送至 QQ 私聊", await feature.toggle("1718018032", is_group=True))
        self.assertEqual(feature.subscribers, [1718018032])
        self.assertIn("群聊", await feature.toggle("123456", is_group=False))

    async def test_kb_watch_toggles_kook_alliance_channel(self):
        feature = self.app.kb_watch
        session = "kook:GroupMessage:channel-1"
        self.assertIn(
            "KOOK 频道",
            await feature.toggle_alliance(session, platform_name="aiocqhttp", is_group=True),
        )
        self.assertIn(
            "订阅成功",
            await feature.toggle_alliance(session, platform_name="kook", is_group=True),
        )
        self.assertEqual(feature.alliance_sessions, [session])
        self.assertIn(
            "取消",
            await feature.toggle_alliance(session, platform_name="kook", is_group=True),
        )
        self.assertEqual(feature.alliance_sessions, [])

    async def test_kb_watch_formats_and_pushes_corporation_kill(self):
        feature = self.app.kb_watch
        feature.catalog.replace_types(
            [EveType(17715, "Gila", "毒蜥级", 26, 161, True)], "kb-watch-test"
        )
        feature.client = Mock()
        feature.client.names.return_value = {
            2123456789: "Target Pilot",
            30000142: "Jita",
        }
        self.notifier.send_private.return_value = True
        package = {
            "killmail_id": 139000001,
            "esi": {
                "killmail_time": "2026-10-09T12:30:00Z",
                "solar_system_id": 30000142,
                "victim": {
                    "character_id": 2123456789,
                    "corporation_id": 98000001,
                    "ship_type_id": 17715,
                },
                "attackers": [{"corporation_id": 98828269, "final_blow": True}],
            },
            "zkb": {"totalValue": 1_250_000_000},
        }
        await feature._process_package(package)
        message = self.notifier.send_private.await_args.args[1]
        self.notifier.send_private.assert_awaited_once_with(1718018032, message)
        self.assertIn("【军团 KB 击杀】", message)
        self.assertIn("角色：Target Pilot", message)
        self.assertIn("舰船：毒蜥级", message)
        self.assertIn("地点：Jita", message)
        self.assertIn("价值：1.25 B ISK", message)
        self.assertIn("时间：10-09 20:30:00 UTC+8", message)
        self.assertIn("https://zkillboard.com/kill/139000001/", message)

        await feature._process_package(package)
        self.notifier.send_private.assert_awaited_once()

    def test_kb_watch_classifies_loss_and_internal_kill(self):
        feature = self.app.kb_watch
        loss = {
            "esi": {
                "victim": {"corporation_id": 98828269},
                "attackers": [{"corporation_id": 98000001}],
            }
        }
        internal = {
            "esi": {
                "victim": {"corporation_id": 98828269},
                "attackers": [{"corporation_id": 98828269}],
            }
        }
        self.assertEqual(feature._event_type(loss), "军团 KB 损失")
        self.assertEqual(feature._event_type(internal), "军团内部损失")

    async def test_kb_watch_pushes_alliance_activity_only_to_kook(self):
        feature = self.app.kb_watch
        session = "kook:GroupMessage:channel-1"
        feature.state["alliance_session_origins"] = [session]
        feature.client = Mock()
        feature.client.names.return_value = {
            2123456789: "Alliance Target",
            30000142: "Jita",
        }
        self.notifier.send_session_card.return_value = True
        package = {
            "killmail_id": 139000002,
            "esi": {
                "killmail_time": "2026-10-09T12:30:00Z",
                "solar_system_id": 30000142,
                "victim": {
                    "character_id": 2123456789,
                    "corporation_id": 98000001,
                    "alliance_id": 99000001,
                    "ship_type_id": 17715,
                },
                "attackers": [
                    {
                        "character_id": 2124698588,
                        "corporation_id": 98000002,
                        "alliance_id": 99007887,
                        "final_blow": True,
                    }
                ],
            },
            "zkb": {"totalValue": 500_000_000},
        }
        await feature._process_package(package)
        card = self.notifier.send_session_card.await_args.args[1]
        self.notifier.send_session_card.assert_awaited_once_with(session, card)
        self.notifier.send_session.assert_not_awaited()
        self.notifier.send_private.assert_not_awaited()
        self.assertEqual(card["theme"], "success")
        self.assertEqual(card["size"], "sm")
        rendered = str(card)
        self.assertIn("联盟 KB 击杀", rendered)
        self.assertIn("images.evetech.net/types/17715/render", rendered)
        self.assertIn("images.evetech.net/characters/2124698588/portrait", rendered)
        self.assertIn("images.evetech.net/characters/2123456789/portrait", rendered)
        self.assertIn("images.evetech.net/corporations/98000002/logo", rendered)
        self.assertIn("images.evetech.net/alliances/99007887/logo", rendered)
        self.assertIn("https://zkillboard.com/kill/139000002/", rendered)
        self.assertNotIn("image-group", rendered)
        self.assertNotIn("size=512", rendered)
        self.assertNotIn("paragraph", rendered)
        self.assertNotIn("action-group", rendered)
        context_rows = [module for module in card["modules"] if module["type"] == "context"]
        self.assertEqual(len(context_rows), 6)
        for row in context_rows[:4]:
            self.assertEqual(len(row["elements"]), 2)
        for emoji in ("⚔", "💀", "📍", "👥", "🕒", "🏢", "🌐"):
            self.assertNotIn(emoji, rendered)

    def test_zkill_live_client_reads_sequence_and_404(self):
        sequence_response = Mock()
        sequence_response.json.return_value = {"sequence": 99933799}
        sequence_response.raise_for_status.return_value = None
        package_response = Mock(status_code=404)
        client = ZkillLiveClient(user_agent="test-agent")
        with patch(
            "plugin.features.kb_watch.client.requests.get",
            side_effect=[sequence_response, package_response],
        ):
            self.assertEqual(client.latest_sequence(), 99933799)
            self.assertIsNone(client.package(99933800))

    def test_kb_client_loads_latest_killmail_details(self):
        client = KbClient()
        summaries = Mock()
        summaries.json.return_value = [
            {
                "killmail_id": 20,
                "killmail_time": "2026-10-10T10:00:00Z",
                "zkb": {"hash": "older-hash", "totalValue": 100},
                "victim": {"character_id": 123},
                "attackers": [],
            },
            {
                "killmail_id": 21,
                "killmail_time": "2026-10-11T10:00:00Z",
                "zkb": {"hash": "newer-hash", "totalValue": 250},
                "victim": {"character_id": 123},
                "attackers": [],
            },
        ]
        summaries.raise_for_status.return_value = None
        details = Mock()
        details.json.return_value = {
            "victim": {"character_id": 123, "damage_taken": 500},
            "attackers": [{"damage_done": 500, "final_blow": True}],
            "killmail_time": "2026-10-11T10:00:00Z",
        }
        details.raise_for_status.return_value = None
        with patch(
            "plugin.features.kb.client.requests.get", side_effect=[summaries, details]
        ) as get:
            result = client.latest_character_killmail(123, "kills")
        self.assertEqual(result["killmail_id"], 21)
        self.assertEqual(result["zkb"]["totalValue"], 250)
        self.assertEqual(result["esi"]["victim"]["damage_taken"], 500)
        self.assertTrue(get.call_args_list[0].args[0].endswith("/123/kills/"))
        self.assertNotIn("/limit/", get.call_args_list[0].args[0])
        self.assertIn("/21/newer-hash/", get.call_args_list[1].args[0])

    def test_kb_client_deduplicates_entity_ids_before_esi_names_request(self):
        client = KbClient()
        response = Mock(status_code=200)
        response.json.return_value = [{"id": 11, "name": "Pilot"}]
        response.raise_for_status.return_value = None
        with patch("plugin.features.kb.client.requests.post", return_value=response) as post:
            names = client.names([11, 22, 11, 0, -1, "22"])
        self.assertEqual(post.call_args.kwargs["json"], [11, 22])
        self.assertEqual(names, {11: "Pilot"})

    def test_kb_client_splits_esi_names_batches_after_validation_error(self):
        client = KbClient()
        rejected = Mock(status_code=400)
        left = Mock(status_code=200)
        left.json.return_value = [{"id": 11, "name": "Pilot One"}]
        right = Mock(status_code=200)
        right.json.return_value = [{"id": 22, "name": "Pilot Two"}]
        with patch(
            "plugin.features.kb.client.requests.post",
            side_effect=[rejected, left, right],
        ) as post:
            names = client.names([11, 22])
        self.assertEqual([call.kwargs["json"] for call in post.call_args_list], [[11, 22], [11], [22]])
        self.assertEqual(names, {11: "Pilot One", 22: "Pilot Two"})

    async def test_kb_recent_query_builds_a_card_with_utc8_location(self):
        feature = self.app.kb
        package = {
            "killmail_id": 139000123,
            "esi": {
                "killmail_time": "2026-10-12T13:40:00Z",
                "solar_system_id": 30000142,
                "victim": {"character_id": 2123456789, "damage_taken": 700},
                "attackers": [],
            },
            "zkb": {"totalValue": 100000, "droppedValue": 50000},
        }
        feature.client.latest_character_killmail = Mock(return_value=package)
        feature.client.names = Mock(
            return_value={2123456789: "Target Pilot", 30000142: "Jita"}
        )
        feature.renderer.render = Mock(return_value="<html>KB image</html>")
        reply = await feature.query_recent("/kbk 2123456789", "kills")
        self.assertIn("Target Pilot", reply.text)
        self.assertIn("2026-10-12 21:40 UTC+8", reply.text)
        self.assertEqual(reply.html, "<html>KB image</html>")
        feature.client.latest_character_killmail.assert_called_once_with(2123456789, "kills")
        feature.renderer.render.assert_called_once_with(package, "角色最近击杀")

    def test_kb_image_renderer_uses_utc8_blue_location_and_participant_details(self):
        renderer = self.app.kb.renderer
        renderer.client.names = Mock(
            return_value={
                2123456789: "Target Pilot",
                30000142: "Jita",
                2123456788: "Final Pilot",
                98000001: "Example Corp",
            }
        )
        renderer.catalog.replace_types(
            [
                EveType(17715, "Gila", "毒蜥级"),
                EveType(28668, "Heavy Missile Launcher II", "重型导弹发射器 II"),
                EveType(28670, "Scourge Heavy Missile", "鞭挞重型导弹"),
                EveType(11105, "Damage Control II", "损伤控制 II"),
            ],
            "kb-render-test",
        )
        package = {
            "killmail_id": 139000124,
            "esi": {
                "killmail_time": "2026-10-12T13:40:00Z",
                "solar_system_id": 30000142,
                "victim": {
                    "character_id": 2123456789,
                    "corporation_id": 98000001,
                    "ship_type_id": 17715,
                    "damage_taken": 1000,
                    "items": [{"item_type_id": 11105, "quantity_dropped": 1}],
                },
                "attackers": [
                    {
                        "character_id": 2123456788,
                        "corporation_id": 98000001,
                        "ship_type_id": 17715,
                        "weapon_type_id": 28670,
                        "damage_done": 1000,
                        "final_blow": True,
                    }
                ],
            },
            "zkb": {"totalValue": 200000, "droppedValue": 50000},
        }
        markup = renderer.render(package, "角色最近击杀")
        self.assertIn("2026-10-12 21:40:00 UTC+8", markup)
        self.assertIn('<strong class="location">Jita</strong>', markup)
        self.assertIn("class=\"final\">最后一击", markup)
        self.assertIn("毒蜥级 / 鞭挞重型导弹", markup)
        self.assertIn("掉落 ×1", markup)

    def test_kb_client_resolves_character_stats_and_affiliations(self):
        client = KbClient(cache_seconds=600)
        identity_response = Mock()
        identity_response.json.return_value = {
            "characters": [{"id": 2124698588, "name": "Yuxan Axiom"}]
        }
        identity_response.raise_for_status.return_value = None
        names_response = Mock()
        names_response.json.return_value = [
            {"id": 98000001, "name": "Example Corporation", "category": "corporation"},
            {"id": 99000001, "name": "Example Alliance", "category": "alliance"},
        ]
        names_response.raise_for_status.return_value = None
        stats_response = Mock()
        stats_response.json.return_value = {
            "info": {
                "name": "Yuxan Axiom",
                "corporationID": 98000001,
                "allianceID": 99000001,
                "security_status": 1.8,
            },
            "dangerRatio": 72,
            "gangRatio": 84,
            "shipsDestroyed": 1284,
            "shipsLost": 96,
            "iskDestroyed": 428_670_000_000,
            "iskLost": 12_430_000_000,
            "soloKills": 37,
            "soloLosses": 8,
        }
        stats_response.raise_for_status.return_value = None
        with (
            patch(
                "plugin.features.kb.client.requests.post",
                side_effect=[identity_response, names_response],
            ) as post,
            patch("plugin.features.kb.client.requests.get", return_value=stats_response) as get,
        ):
            first = client.query("Yuxan Axiom")
            second = client.query("yuxan axiom")
        self.assertIs(first, second)
        self.assertEqual(first.corporation_name, "Example Corporation")
        self.assertEqual(first.alliance_name, "Example Alliance")
        self.assertEqual(post.call_count, 2)
        get.assert_called_once()


class FormattingTests(unittest.TestCase):
    def test_help_text_is_compact_and_lists_supported_commands(self):
        text = HelpFeature.TEXT
        self.assertTrue(text.startswith("【烟雨机器人插件帮助】\n"))
        self.assertNotIn("\n\n", text)
        for command in (
            "/油价 河南",
            "/jt 毒蜥级",
            "/col 中级水晶",
            "/金币比例",
            "/rat",
            "/info",
            "/kb Yuxan Axiom",
            "/timer 2天2小时5分",
            "/status",
            "/subkb",
            "/suballkb",
        ):
            self.assertIn(command, text)
        self.assertEqual(text.count("需在管理系统注册"), 2)

    def test_timer_accepts_supported_duration_formats(self):
        expected = dt.timedelta(days=2, hours=2, minutes=5)
        for value in (
            "2天2小时5分",
            "2天 2小时 5分钟",
            "2.2.5",
            "2 2 5",
            "2:2:5",
            "2/2/5",
            "2d2h5m",
            "2 days 2 hours 5 minutes",
        ):
            with self.subTest(value=value):
                self.assertEqual(TimerFeature.parse_duration(value), expected)

    def test_timer_accepts_partial_unit_formats(self):
        self.assertEqual(TimerFeature.parse_duration("2小时5分"), dt.timedelta(hours=2, minutes=5))
        self.assertEqual(TimerFeature.parse_duration("5m"), dt.timedelta(minutes=5))
        self.assertEqual(TimerFeature.parse_duration("2.5"), dt.timedelta(hours=2, minutes=5))
        self.assertEqual(TimerFeature.parse_duration("5"), dt.timedelta(minutes=5))

    def test_timer_rejects_invalid_or_zero_duration(self):
        for value in ("", "0.0.0", "两天", "2天abc", "2天3天"):
            with self.subTest(value=value):
                self.assertIsNone(TimerFeature.parse_duration(value))

    def test_timer_formats_eve_and_beijing_deadlines(self):
        now = dt.datetime(2026, 10, 3, 20, 30, tzinfo=dt.timezone.utc)
        self.assertEqual(
            TimerFeature.format_deadline(dt.timedelta(hours=5), now),
            "EVE时间：10-04 01:30\n北京时间：10-04 09:30",
        )

    def test_egg_arguments(self):
        self.assertEqual(parse_egg_args("/蛋价 平舆 20260911"), ("平舆", "20260911"))
        self.assertEqual(parse_egg_args("蛋价"), ("", None))

    def test_oil_change_ignores_date(self):
        self.assertFalse(
            has_oil_price_changed({"p92": "7", "date": "old"}, {"p92": "7", "date": "new"})
        )
        self.assertTrue(has_oil_price_changed({"p92": "7"}, {"p92": "8"}))

    def test_zero_distance_is_not_divided(self):
        self.assertIn("必须大于 0", calculate_oil_cost("92", 7.5, 8, 0))
