import unittest
from unittest.mock import Mock, patch

from plugin.features.fleet.client import FleetInviteClient
from plugin.features.fleet.service import FleetFeature
from plugin.features.where.client import AssetSearchClient
from plugin.features.where.service import WhereFeature


class WhereFleetTests(unittest.IsolatedAsyncioTestCase):
    async def test_where_paginates_and_shows_location(self):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {
            "code": 0,
            "data": {
                "total": 21,
                "items": [
                    {
                        "characterName": "Alpha",
                        "typeName": "乌鸦级",
                        "quantity": 2,
                        "locationName": "吉他 IV-4",
                        "containerName": "货柜",
                    }
                ],
            },
        }
        with patch("plugin.features.where.client.requests.get", return_value=response) as get:
            result = await WhereFeature(AssetSearchClient()).query("/where 乌鸦级", "1718018032")
        get.assert_called_once_with(
            "https://admin-api.oofo.cc/game/eve/public/users/by-qq/1718018032/assets/search",
            params={"keyword": "乌鸦级", "page": 1},
            timeout=15,
        )
        self.assertIn("Alpha · 乌鸦级 ×2 · 吉他 IV-4 / 货柜", result)
        self.assertIn("page=2", result)

    async def test_fleet_all_and_partial_failure(self):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {
            "code": 0,
            "data": {
                "mainCharacter": "Main Pilot",
                "succeeded": 1,
                "failed": 1,
                "characters": [
                    {"characterName": "Alt One", "success": True, "message": "等待接受"},
                    {"characterName": "Alt Two", "success": False, "message": "CSPA 收费"},
                ],
            },
        }
        with patch("plugin.features.fleet.client.requests.post", return_value=response) as post:
            result = await FleetFeature(FleetInviteClient()).query(
                '/fleet "Main Pilot" all', "1718018032"
            )
        post.assert_called_once_with(
            "https://admin-api.oofo.cc/game/eve/public/users/by-qq/1718018032/fleet/invitations",
            json={"mainCharacter": "Main Pilot", "target": "all"},
            timeout=30,
        )
        self.assertIn("成功 1，失败 1", result)
        self.assertIn("Alt Two：CSPA 收费", result)

    async def test_fleet_usage_and_binding_error(self):
        feature = FleetFeature(FleetInviteClient())
        self.assertIn("用法", await feature.query("/fleet Main Pilot ALL", "1718018032"))
        self.assertIn(
            "无法获取有效的用户 QQ", await feature.query('/fleet "Main Pilot" ALL', "bad")
        )
        response = Mock(ok=False, status_code=404)
        response.json.return_value = {"code": 46104, "message": "没有找到该QQ号的EVE绑定信息"}
        with patch("plugin.features.fleet.client.requests.post", return_value=response):
            result = await feature.query('/fleet "Main Pilot" ALL', "1718018032")
        self.assertIn("绑定角色", result)

        response.json.return_value = {"code": 404, "message": "主角色与QQ不匹配"}
        with patch("plugin.features.fleet.client.requests.post", return_value=response):
            result = await feature.query('/fleet "Main Pilot" ALL', "1718018032")
        self.assertIn("主角色与QQ不匹配", result)
