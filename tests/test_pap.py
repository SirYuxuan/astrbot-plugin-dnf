import unittest
from unittest.mock import Mock, patch

import requests

from plugin.features.pap.client import PapClient
from plugin.features.pap.service import PAP_BINDING_HINT, PapFeature


class PapClientTests(unittest.TestCase):
    def test_user_and_ranking_request_exact_urls(self):
        response = Mock()
        response.json.return_value = {"code": 0, "data": {"message": "PAP 报告"}}
        client = PapClient(timeout=7)
        with patch("plugin.features.pap.client.requests.get", return_value=response) as get:
            client.query("12345678")
            get.assert_called_with(
                "https://dijiuren.top/api/game/eve/public/pap/users/by-qq/12345678", timeout=7
            )
            client.ranking()
            get.assert_called_with(PapClient.RANKING_URL, timeout=7)

    def test_http_errors_are_not_treated_as_user_not_found(self):
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError()
        with patch("plugin.features.pap.client.requests.get", return_value=response):
            with self.assertRaises(requests.HTTPError):
                PapClient().query("12345678")

    def test_json_resource_not_found_preserves_business_message(self):
        response = Mock(status_code=404)
        response.json.return_value = {"code": 40400, "message": "资源不存在"}
        with patch("plugin.features.pap.client.requests.get", return_value=response):
            result = PapClient().query("12345678")
        self.assertEqual(PapFeature.format_response(result), PAP_BINDING_HINT)
        response.raise_for_status.assert_not_called()


class PapFeatureTests(unittest.IsolatedAsyncioTestCase):
    async def test_qq_validation_and_message_response(self):
        client = Mock()
        client.query.return_value = {"code": 0, "data": {"message": "个人 PAP 报告"}}
        feature = PapFeature(client)
        self.assertEqual(await feature.query(" 12345678 "), "个人 PAP 报告")
        client.query.assert_called_once_with("12345678")
        client.query.reset_mock()
        self.assertIn("有效", await feature.query("not-qq"))
        client.query.assert_not_called()

    async def test_ranking_does_not_require_qq(self):
        client = Mock()
        client.ranking.return_value = {"code": 0, "data": {"message": "PAP Top10"}}
        self.assertEqual(await PapFeature(client).ranking(), "PAP Top10")
        client.ranking.assert_called_once_with()

    async def test_http404_and_timeout_have_clear_errors(self):
        client = Mock()
        response = requests.Response()
        response.status_code = 404
        client.query.side_effect = requests.HTTPError(response=response)
        with self.assertLogs("plugin.features.pap.service", level="WARNING"):
            self.assertIn("HTTP 404", await PapFeature(client).query("12345678"))
        client.ranking.side_effect = requests.Timeout()
        with self.assertLogs("plugin.features.pap.service", level="ERROR"):
            self.assertIn("查询失败", await PapFeature(client).ranking())

    def test_missing_fields_are_not_replaced_by_zero(self):
        with self.assertRaises(ValueError):
            PapFeature.format_response({"data": {"available": 0}})
        self.assertEqual(PapFeature.format_response({"code": 1, "message": "尚未绑定"}), "尚未绑定")
        self.assertEqual(PapFeature.format_response({"code": 0, "data": []}), "暂无 PAP 数据。")

    def test_real_ranking_schema_sorted_and_limited(self):
        data = [{"rank": i, "nickname": f"Pilot {i}", "income": 1000 - i} for i in range(12, 0, -1)]
        text = PapFeature.format_response({"code": 0, "data": data}, ranking=True)
        self.assertTrue(text.startswith("【PAP 累计获得 Top10】\n1. Pilot 1：999 PAP"))
        self.assertIn("10. Pilot 10：990 PAP", text)
        self.assertNotIn("Pilot 11", text)

    async def test_invalid_ranking_is_not_reported_as_zero(self):
        client = Mock()
        client.ranking.return_value = {"code": 0, "data": [{"nickname": "Pilot"}]}
        with self.assertLogs("plugin.features.pap.service", level="ERROR"):
            self.assertIn("查询失败", await PapFeature(client).ranking())

    def test_real_user_schema_and_zero_balances(self):
        payload = {
            "code": 0,
            "data": {
                "available": 8,
                "characterCount": 4,
                "frozen": 0,
                "income": 28,
                "nickname": "测试昵称",
                "spent": 20,
            },
        }
        self.assertEqual(
            PapFeature.format_response(payload),
            "【个人 PAP】\n昵称：测试昵称\n角色数：4\n可用 PAP：8\n冻结 PAP：0\n累计获得：28\n累计使用：20",
        )
        for key in ("available", "income", "spent"):
            payload["data"][key] = 0
        self.assertIn("可用 PAP：0", PapFeature.format_response(payload))

    def test_missing_user_is_binding_hint_only_for_personal_query(self):
        payload = {"code": 40400, "message": "资源不存在"}
        self.assertEqual(PapFeature.format_response(payload), PAP_BINDING_HINT)
        self.assertEqual(PapFeature.format_response(payload, ranking=True), "资源不存在")

    async def test_personal_query_formats_real_response(self):
        client = Mock()
        client.query.return_value = {
            "code": 0,
            "data": {
                "nickname": "测试昵称",
                "characterCount": 4,
                "available": 8,
                "frozen": 0,
                "income": 28,
                "spent": 20,
            },
        }
        self.assertIn("可用 PAP：8", await PapFeature(client).query("12345678"))
        client.query.return_value = {"code": 40400, "message": "资源不存在"}
        self.assertEqual(await PapFeature(client).query("12345678"), PAP_BINDING_HINT)
