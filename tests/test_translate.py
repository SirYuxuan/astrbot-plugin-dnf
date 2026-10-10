import unittest
from unittest.mock import Mock, patch

import requests

from plugin.features.translate.client import TranslateClient
from plugin.features.translate.service import TranslateFeature


class TranslateTests(unittest.IsolatedAsyncioTestCase):
    async def test_english_name_and_optional_kind(self):
        response = Mock()
        response.json.return_value = {
            "code": 0,
            "data": {
                "sourceLanguage": "en",
                "targetLanguage": "zh",
                "matches": [
                    {
                        "kind": "type",
                        "id": 638,
                        "nameEn": "Raven",
                        "nameZh": "乌鸦级",
                        "translation": "乌鸦级",
                    }
                ],
            },
        }
        feature = TranslateFeature(TranslateClient())
        with patch("plugin.features.translate.client.requests.get", return_value=response) as get:
            result = await feature.query("/tr kind=TYPE raven")
        get.assert_called_once_with(
            "https://admin-api.oofo.cc/game/eve/public/translate",
            params={"q": "raven", "kind": "type"},
            timeout=10,
        )
        self.assertEqual(result, "EVE 名称翻译：Raven → 乌鸦级（type ID 638）")

    async def test_ambiguous_chinese_name_lists_each_id(self):
        response = Mock()
        response.json.return_value = {
            "code": 0,
            "data": {
                "sourceLanguage": "zh",
                "targetLanguage": "en",
                "matches": [
                    {"kind": "type", "id": 638, "nameZh": "乌鸦级", "translation": "Raven"},
                    {"kind": "type", "id": 49118, "nameZh": "乌鸦级", "translation": "Raven Hulk"},
                ],
            },
        }
        feature = TranslateFeature(TranslateClient())
        with patch("plugin.features.translate.client.requests.get", return_value=response):
            result = await feature.query("/tr 乌鸦级")
        self.assertIn("找到 2 个候选（中→英）", result)
        self.assertIn("type ID 638", result)
        self.assertIn("type ID 49118", result)

    async def test_usage_empty_result_and_network_failure(self):
        feature = TranslateFeature(TranslateClient())
        with patch("plugin.features.translate.client.requests.get") as get:
            self.assertIn("用法", await feature.query("/tr"))
            self.assertIn("不支持的分类", await feature.query("/tr kind=bad Raven"))
            get.assert_not_called()
        response = Mock()
        response.json.return_value = {"code": 0, "data": {"matches": []}}
        with patch("plugin.features.translate.client.requests.get", return_value=response):
            self.assertIn("没有找到", await feature.query("/tr unknown"))
        with patch(
            "plugin.features.translate.client.requests.get",
            side_effect=requests.Timeout,
        ):
            self.assertIn("暂时不可用", await feature.query("/tr Raven"))
