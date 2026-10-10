import unittest
from unittest.mock import Mock, patch

from plugin.features.ship_training.service import ShipTrainingFeature


class ShipTrainingTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_uses_sender_qq_and_ship_name(self):
        response = Mock()
        response.json.return_value = {
            "code": 0,
            "data": {
                "ship": {"name": "乌鸦级"},
                "characters": [
                    {"name": "Yuxan Axiom", "missingSp": 39227, "immediateSeconds": 40933},
                    {"name": "Yuxan Hauler", "missingSp": 121500, "immediateSeconds": 158480},
                    {"name": "Yuxan Capital", "missingSp": 158133, "immediateSeconds": 316266},
                    {"name": "Yuxan Indy01", "missingSp": 158755, "immediateSeconds": 317510},
                    {"name": "Yuxan Trade", "error": "尚无属性快照，请同步角色技能"},
                ],
            },
        }
        feature = ShipTrainingFeature()
        with patch(
            "plugin.features.ship_training.service.requests.get", return_value=response
        ) as get:
            text = await feature.query("/train 乌鸦级", "1718018032")
        get.assert_called_once_with(
            "https://admin-api.oofo.cc/game/eve/public/users/by-qq/1718018032/ship-training",
            params={"ship": "乌鸦级"},
            timeout=15,
        )
        self.assertEqual(
            text,
            "乌鸦级舰船训练\n"
            "Yuxan Axiom：缺 39,227 SP｜11小时23分\n"
            "Yuxan Hauler：缺 121,500 SP｜1天20小时2分\n"
            "Yuxan Capital：缺 158,133 SP｜3天15小时52分\n"
            "Yuxan Indy01：缺 158,755 SP｜3天16小时12分\n"
            "Yuxan Trade：尚无属性快照，请同步角色技能",
        )
        self.assertNotIn("队列", text)

    async def test_usage_and_invalid_qq_skip_request(self):
        feature = ShipTrainingFeature()
        with patch("plugin.features.ship_training.service.requests.get") as get:
            self.assertEqual(await feature.query("/train", "1718018032"), "用法：/train 乌鸦级")
            self.assertEqual(await feature.query("/train 乌鸦级", "abc"), "无法获取有效的用户 QQ")
        get.assert_not_called()

    async def test_ready_error_and_missing_binding(self):
        feature = ShipTrainingFeature()
        response = Mock()
        response.json.return_value = {
            "code": 0,
            "data": {"characters": [{"name": "Pilot", "ready": True}]},
        }
        with patch("plugin.features.ship_training.service.requests.get", return_value=response):
            self.assertEqual(
                await feature.query("/train Raven", "1718018032"),
                "Raven舰船训练\nPilot：已具备驾驶技能",
            )
        response.json.return_value = {"code": 46104, "message": "没有找到该QQ号的EVE绑定信息"}
        with patch("plugin.features.ship_training.service.requests.get", return_value=response):
            self.assertIn("请先注册eve.oofo.cc", await feature.query("/train Raven", "1718018032"))
