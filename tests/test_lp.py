import unittest
from unittest.mock import Mock, patch

import requests

from plugin.features.lp.client import LpClient
from plugin.features.lp.service import LpFeature


class LpTests(unittest.IsolatedAsyncioTestCase):
    def test_client_formats_message_and_sends_character(self):
        response = Mock()
        response.json.return_value = {"code": 0, "data": {"message": "净利润：1,176,915,365.20 ISK"}}
        response.raise_for_status.return_value = None
        with patch("plugin.features.lp.client.requests.get", return_value=response) as get:
            result = LpClient().query("101", "Yuxan Nova")
        self.assertIn("净利润", result)
        get.assert_called_once_with(
            "https://admin-api.oofo.cc/game/eve/public/users/by-qq/101/lp",
            params={"qq": "101", "character": "Yuxan Nova"},
            timeout=15,
        )

    def test_legacy_query_endpoint_falls_back(self):
        failed = requests.ConnectionError("old path")
        response = Mock()
        response.text = "legacy"
        response.json.side_effect = ValueError
        response.raise_for_status.return_value = None
        with patch("plugin.features.lp.client.requests.get", side_effect=[failed, response]) as get:
            self.assertEqual(LpClient("https://example.test/lp/{qq}").query("101"), "legacy")
        self.assertEqual(get.call_args_list[1].kwargs["params"], {"qq": "101"})

    async def test_service_parses_command_and_validates_qq(self):
        client = Mock()
        client.query.return_value = "报告"
        feature = LpFeature(client)
        self.assertEqual(await feature.query("/lp Yuxan Nova", "101344113"), "报告")
        client.query.assert_called_once_with("101344113", "Yuxan Nova")
        self.assertIn("有效", await feature.query("/lp", "0"))
