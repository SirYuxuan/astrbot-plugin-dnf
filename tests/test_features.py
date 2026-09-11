import asyncio
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from plugin.application import PluginApplication
from plugin.core.config import PluginConfig
from plugin.core.storage import JsonFileStore
from plugin.features.egg.client import parse_egg_args
from plugin.features.gold.service import GoldFeature
from plugin.features.oil.client import calculate_oil_cost, has_oil_price_changed


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

    async def test_oil_startup_does_not_commit_without_delivery(self):
        self.notifier.send_group.return_value = False
        with patch("plugin.features.oil.service.fetch_oil_data", return_value=self.oil_data):
            await self.app.oil._send_startup_notice()
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


class FormattingTests(unittest.TestCase):
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
