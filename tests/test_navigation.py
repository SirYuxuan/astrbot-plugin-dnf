import unittest
from unittest.mock import Mock, patch

import requests

from plugin.features.navigation.client import WaypointClient
from plugin.features.navigation.service import NavigationFeature


class NavigationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.feature = NavigationFeature(WaypointClient())

    async def test_all_and_partial_failure_are_reported_per_character(self):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {
            "code": 0,
            "data": {
                "destinationName": "吉他",
                "total": 2,
                "succeeded": 1,
                "failed": 1,
                "characters": [
                    {"characterName": "Pilot One", "success": True, "message": "已设置导航"},
                    {
                        "characterName": "Pilot Two",
                        "success": False,
                        "message": "缺少 esi-ui.write_waypoint.v1 授权",
                    },
                ],
            },
        }
        with patch(
            "plugin.features.navigation.client.requests.post", return_value=response
        ) as post:
            result = await self.feature.query("/nav all 吉他", "1718018032")
        post.assert_called_once_with(
            "https://admin-api.oofo.cc/game/eve/public/users/by-qq/1718018032/waypoint",
            json={"characterName": "ALL", "destination": "吉他"},
            timeout=15,
        )
        self.assertIn("成功 1，失败 1", result)
        self.assertIn("✅ Pilot One：已设置导航", result)
        self.assertIn("❌ Pilot Two：缺少 esi-ui.write_waypoint.v1 授权", result)

    async def test_quoted_names_and_destination_id(self):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {
            "code": 0,
            "data": {
                "destinationName": "New Caldari",
                "characters": [{"characterName": "Yuxan Axiom", "success": True}],
            },
        }
        with patch(
            "plugin.features.navigation.client.requests.post", return_value=response
        ) as post:
            result = await self.feature.query('/nav "Yuxan Axiom" "New Caldari"', "1718018032")
        self.assertIn("Yuxan Axiom", result)
        self.assertEqual(
            post.call_args.kwargs["json"],
            {"characterName": "Yuxan Axiom", "destination": "New Caldari"},
        )

    async def test_usage_invalid_qq_and_api_errors(self):
        with patch("plugin.features.navigation.client.requests.post") as post:
            self.assertIn("用法", await self.feature.query("/nav", "1718018032"))
            self.assertIn("用法", await self.feature.query("/nav ALL", "1718018032"))
            self.assertIn("无法获取有效的用户 QQ", await self.feature.query("/nav ALL 吉他", "bad"))
            post.assert_not_called()

        for status, message, expected in (
            (404, "目的地星系不存在", "目的地星系不存在"),
            (404, "角色找不到", "没有找到指定角色"),
            (404, "QQ 未绑定", "请先注册eve.oofo.cc"),
            (429, "请求过于频繁", "稍后重试"),
        ):
            with self.subTest(status=status, message=message):
                response = Mock(ok=False, status_code=status)
                response.json.return_value = {"code": status, "message": message}
                with patch(
                    "plugin.features.navigation.client.requests.post", return_value=response
                ):
                    self.assertIn(expected, await self.feature.query("/nav ALL 吉他", "1718018032"))

        with patch("plugin.features.navigation.client.requests.post", side_effect=requests.Timeout):
            self.assertIn("暂时不可用", await self.feature.query("/nav ALL 吉他", "1718018032"))
