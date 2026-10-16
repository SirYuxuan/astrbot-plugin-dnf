import datetime as dt
import unittest
from unittest.mock import Mock, patch

import requests

from plugin.features.kb.client import KbClient
from plugin.features.kb.profile_client import KbProfileClient
from plugin.features.kb.profile_renderer import KbProfileRenderer
from plugin.features.kb.renderer import KbKillmailRenderer
from plugin.features.kb.service import KbFeature


def record(kid=1, *, loss=False):
    return {
        "killmail_id": kid,
        "killmail_time": "2026-10-15T20:30:00Z",
        "solar_system_id": 30000142,
        "victim": {"character_id": 123 if loss else 999, "ship_type_id": 34},
        "attackers": [{"character_id": 999 if loss else 123, "ship_type_id": 35}],
        "zkb": {"totalValue": 100000000},
    }


def profile():
    return {
        "identity": (123, "Pilot <A>"),
        "character": {"corporation_id": 456, "birthday": "2026-01-01T00:00:00Z"},
        "stats": {"shipsDestroyed": 2, "shipsLost": 1, "iskDestroyed": 200, "iskLost": 100},
        "history": [{"corporation_id": 456, "start_date": "2026-10-10T00:00:00Z"}],
        "names": {456: "Corp <B>", 30000142: "Jita"},
        "records": [record(), record(2, loss=True)],
        "warnings": [],
    }


class ProfileClientTests(unittest.TestCase):
    def setUp(self):
        self.client = KbClient()
        self.client.resolve_character = Mock(return_value=(123, "Pilot A"))
        self.client.names = Mock(return_value={456: "Corp"})
        self.loader = KbProfileClient(self.client)

    def test_fetches_full_stats_hydrates_details_and_caches_normalized_name(self):
        summary = {"killmail_id": 2, "zkb": {"hash": "hash", "totalValue": 123}}
        self.loader._get = Mock(
            side_effect=[{"corporation_id": 456}, {"shipsDestroyed": 1}, [], [summary], record(2)]
        )
        result = self.loader.query("Pilot A")
        self.assertEqual(result["records"][0]["zkb"]["totalValue"], 123)
        self.assertIn("/api/stats/characterID/123/", self.loader._get.call_args_list[1].args[0])
        self.assertNotIn("/kills/", self.loader._get.call_args_list[1].args[0])
        count = self.loader._get.call_count
        result["records"].clear()
        again = self.loader.query("  PILOT   A ")
        self.assertEqual(len(again["records"]), 1)
        self.assertEqual(self.loader._get.call_count, count)

    def test_pagination_deduplicates_and_caps_at_400(self):
        self.loader._get = Mock(
            side_effect=[
                {"corporation_id": 456},
                {},
                [],
                [record(i) for i in range(1, 201)],
                [record(i) for i in range(200, 400)],
                [record(400), record(401)],
            ]
        )
        result = self.loader.query("Pilot A")
        self.assertEqual(len(result["records"]), 400)
        self.assertEqual(len({r["killmail_id"] for r in result["records"]}), 400)

    def test_not_found_and_partial_failures_are_explicit(self):
        self.client.resolve_character.return_value = None
        self.assertIsNone(self.loader.query("missing"))
        self.client.resolve_character.return_value = (123, "Pilot A")
        self.loader._get = Mock(
            side_effect=[{"corporation_id": 456}, {}, requests.Timeout(), requests.Timeout()]
        )
        result = self.loader.query("Pilot A")
        self.assertEqual(result["records"], [])
        self.assertIn("军团历史", result["warnings"])
        self.assertIn("近期 KM 抽样不完整", result["warnings"])


class ProfileRendererTests(unittest.TestCase):
    def test_real_sections_utc8_escape_font_and_crop(self):
        catalog = Mock()
        catalog.get_type.side_effect = lambda tid: Mock(name_zh=f"舰船{tid}", name_en="Ship")
        renderer = KbProfileRenderer(catalog)
        markup = renderer.render(profile(), now=dt.datetime(2026, 10, 16, tzinfo=dt.timezone.utc))
        self.assertIn("Pilot &lt;A&gt;", markup)
        self.assertIn("Corp &lt;B&gt;", markup)
        self.assertIn("10-16 04:30", markup)
        self.assertIn("舰船35", markup)
        self.assertIn("舰船34", markup)
        self.assertIn("抽样 <b>2 条</b>", markup)
        self.assertIn("data:font/woff2;base64,", markup)
        self.assertEqual(markup.count('class="km-row"'), 2)
        opts = KbKillmailRenderer.image_render_options(markup)
        self.assertEqual(opts["viewport_width"], 748)
        self.assertFalse(opts["full_page"])

    def test_empty_activity_and_partial_history_do_not_break_card(self):
        data = profile()
        data.update(records=[], history=[], stats={}, warnings=["军团历史"])
        catalog = Mock()
        catalog.get_type.return_value = None
        markup = KbProfileRenderer(catalog).render(data)
        self.assertIn("暂无公开 KM 记录", markup)
        self.assertIn("部分数据暂不可用：军团历史", markup)
        self.assertIn("无联盟", markup)


class ProfileFeatureTests(unittest.IsolatedAsyncioTestCase):
    async def test_usage_missing_upstream_failure_and_render_fallback(self):
        feature = KbFeature(KbClient())
        with patch.object(feature.profile_client, "query") as query:
            self.assertIn("用法", (await feature.query_info("/kbinfo")).text)
            query.assert_not_called()
            query.return_value = None
            self.assertIn("未找到角色", (await feature.query_info("/kbinfo Missing Pilot")).text)
            query.return_value = profile()
            reply = await feature.query_info("/kbinfo Pilot  A")
            query.assert_called_with("Pilot  A")
            self.assertIn("击毁：2", reply.text)
            self.assertEqual(reply.html, "")
            query.side_effect = requests.Timeout()
            with self.assertLogs("plugin.features.kb.service", level="ERROR"):
                self.assertIn("查询失败", (await feature.query_info("/kbinfo Pilot A")).text)
