import unittest
from unittest.mock import Mock, patch

from plugin.features.ship.client import ShipClient
from plugin.features.ship.renderer import ShipCardRenderer
from plugin.features.ship.service import ShipFeature

SHIP_PAYLOAD = {
    "code": 0,
    "message": "ok",
    "data": {
        "typeId": 638,
        "name": "乌鸦级",
        "nameEn": "Raven",
        "description": "乌鸦级战列舰是加达里海军的力量泉源。",
        "slots": {"high": 7, "mid": 7, "low": 5, "rig": 3},
        "hardpoints": {"turret": 4, "launcher": 6},
        "roleBonuses": [{"text": "护盾扩展装置护盾值加成", "value": 100, "unitId": 105}],
        "skillBonuses": [
            {
                "skillName": "加达里战列舰操作",
                "skillTypeId": 3338,
                "bonuses": [{"text": "巡航导弹和鱼雷最大飞行速度加成", "value": 10, "unitId": 105}],
            }
        ],
    },
}


class ShipTests(unittest.IsolatedAsyncioTestCase):
    def test_client_uses_returned_type_id_for_image(self):
        info_response = Mock()
        info_response.json.return_value = SHIP_PAYLOAD
        image_response = Mock()
        image_response.headers = {"Content-Type": "image/png"}
        image_response.content = b"real-png"
        client = ShipClient(timeout=7)
        with patch(
            "plugin.features.ship.client.requests.get",
            side_effect=[info_response, image_response],
        ) as get:
            ship = client.query("乌鸦级")
        self.assertEqual(ship.type_id, 638)
        self.assertTrue(ship.image_data_url.startswith("data:image/png;base64,"))
        self.assertEqual(
            get.call_args_list[0].args,
            ("https://admin-api.oofo.cc/game/eve/public/ships/info",),
        )
        self.assertEqual(get.call_args_list[0].kwargs, {"params": {"name": "乌鸦级"}, "timeout": 7})
        self.assertEqual(
            get.call_args_list[1].args,
            ("https://admin-api.oofo.cc/game/eve/assets/types/638/icon",),
        )

    def test_client_surfaces_not_found_message(self):
        response = Mock()
        response.json.return_value = {"code": 40496, "message": "未找到该舰船"}
        response.raise_for_status.side_effect = RuntimeError("raw HTTP error")
        with patch("plugin.features.ship.client.requests.get", return_value=response):
            with self.assertRaisesRegex(ValueError, "未找到该舰船"):
                ShipClient().query("不存在的舰船")

    async def test_feature_builds_compact_html_card_with_embedded_ship_image(self):
        client = ShipClient()
        ship = self._ship(client)
        with patch.object(client, "query") as query:
            query.return_value = ship
            reply = await ShipFeature(client, ShipCardRenderer()).query("/ship 乌鸦级")
        self.assertEqual(reply.text, "乌鸦级 (Raven) 舰船资料")
        self.assertIn("width:620px", reply.html)
        self.assertIn('src="data:image/png;base64,AA=="', reply.html)
        self.assertIn("高槽", reply.html)
        self.assertIn("+100%", reply.html)
        self.assertIn("加达里战列舰操作", reply.html)

    async def test_feature_requires_ship_name(self):
        client = Mock()
        reply = await ShipFeature(client).query("/ship")
        self.assertEqual(reply.text, "用法：/ship 乌鸦级")
        self.assertIsNone(reply.html)
        client.query.assert_not_called()

    @staticmethod
    def _ship(client: ShipClient):
        with patch(
            "plugin.features.ship.client.requests.get",
            side_effect=ShipTests._responses(),
        ):
            return client.query("乌鸦级")

    @staticmethod
    def _responses():
        info_response = Mock()
        info_response.json.return_value = SHIP_PAYLOAD
        image_response = Mock()
        image_response.headers = {"Content-Type": "image/png"}
        image_response.content = b"\x00"
        return [info_response, image_response]
