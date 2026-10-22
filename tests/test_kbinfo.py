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
        self.assertTrue(opts["full_page"])
        self.assertNotIn("clip", opts)

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


class AssessmentTests(unittest.IsolatedAsyncioTestCase):
    def test_missing_months_unknown_solo_and_old_sample(self):
        from plugin.features.kb.assessment import build_assessment

        data = profile()
        data["records"][0]["killmail_time"] = "2024-01-01T00:00:00Z"
        data["records"] = data["records"][:1]
        a = build_assessment(data, now=dt.datetime(2026, 10, 22, tzinfo=dt.timezone.utc))
        self.assertIsNone(a["scores"]["出勤"])
        self.assertIsNone(a["scores"]["单兵"])
        self.assertIsNone(a["fleet"])
        self.assertGreater(a["facts"]["最近公开KM距今天数"], 365)
        data["stats"].update(months={"202410": {"shipsDestroyed": 1000}}, soloKills=1)
        a = build_assessment(data, now=dt.datetime(2026, 10, 22, tzinfo=dt.timezone.utc))
        self.assertEqual(a["scores"]["出勤"], 0)
        self.assertEqual(a["scores"]["单兵"], 5)

    async def test_ai_success_escape_and_failure_keep_report(self):
        import json
        from unittest.mock import AsyncMock

        feature = KbFeature(KbClient(), KbKillmailRenderer(Mock(), Mock()))
        feature.renderer.catalog.get_type.return_value = None
        payload = dict(
            label="<AI>",
            summary="近期样本有限",
            strengths=["累计战绩可参考"],
            weaknesses=["缺少月度统计"],
            conclusion="谨慎判断",
            recruiter="核实角色定位",
            opponent="观察近期舰船",
        )
        with patch.object(feature.profile_client, "query", return_value=profile()):
            ai = AsyncMock(return_value=json.dumps(payload))
            reply = await feature.query_info("/kbinfo Pilot", commentator=ai)
            self.assertIn("&lt;AI&gt;", reply.html)
            self.assertIn("当前会话模型点评", reply.text)
            self.assertIn("样本不足", reply.text)
            ai.assert_awaited_once()
            for response in ("invalid JSON", '{"label":"bad"}'):
                with self.assertLogs("plugin.features.kb.service", level="WARNING"):
                    reply = await feature.query_info(
                        "/kbinfo Pilot", commentator=AsyncMock(return_value=response)
                    )
                self.assertIn("AI 点评暂不可用", reply.html)
                self.assertIn("角色军团历史", reply.html)

    async def test_session_provider_is_used_without_conversation_history(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from plugin.adapters.astrbot.kb_assessment import session_commentator

        context = SimpleNamespace(
            get_current_chat_provider_id=AsyncMock(return_value="session-model"),
            llm_generate=AsyncMock(return_value=SimpleNamespace(completion_text="{}")),
        )
        self.assertEqual(await session_commentator(context, "group:123")("facts"), "{}")
        context.get_current_chat_provider_id.assert_awaited_once_with("group:123")
        self.assertEqual(
            context.llm_generate.await_args.kwargs["chat_provider_id"], "session-model"
        )
        self.assertNotIn("contexts", context.llm_generate.await_args.kwargs)
