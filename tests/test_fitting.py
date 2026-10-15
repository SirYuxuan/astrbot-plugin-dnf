import asyncio
import unittest
from unittest.mock import Mock, patch

import requests

from plugin.features.fitting.client import FittingClient, FittingImportError
from plugin.features.fitting.service import FittingFeature

FITTING = "[Rifter, Travel]\nDamage Control II\n1MN Afterburner II\n[Empty High slot]"


class FittingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = Mock()
        self.feature = FittingFeature(self.client)

    async def send(self, text, qq="1718018032", origin="qq:private", start=False):
        return await self.feature.handle(origin, qq, text, is_private=True, start=start)

    async def ready(self):
        await self.send("/fitt", start=True)
        await self.send("Yuxan Axiom")

    async def test_isolation_multiline_and_single_submission(self):
        await self.ready()
        self.assertIsNone(await self.send(FITTING, qq="12345678"))
        self.assertIsNone(await self.send(FITTING, origin="other-platform"))
        self.assertIn("导入成功", await self.send("```text\n" + FITTING + "\n```"))
        self.assertIsNone(await self.send(FITTING))
        self.client.import_fitting.assert_called_once_with("1718018032", "Yuxan Axiom", FITTING)

    async def test_group_cannot_start_or_consume_private_session(self):
        await self.ready()
        self.assertIn(
            "仅限私聊",
            await self.feature.handle(
                "qq:private", "1718018032", "/fitt", is_private=False, start=True
            ),
        )
        self.assertIsNone(
            await self.feature.handle("qq:private", "1718018032", FITTING, is_private=False)
        )
        self.client.import_fitting.assert_not_called()
        self.assertEqual(next(iter(self.feature.sessions.values())).character, "Yuxan Axiom")

    async def test_cancel_restart_expiry_and_other_commands(self):
        await self.ready()
        self.assertIn("请输入角色名", await self.send("/fitt", start=True))
        self.assertEqual(next(iter(self.feature.sessions.values())).character, "")
        self.assertIn("取消", await self.send("/cancel"))
        await self.ready()
        self.assertIsNone(await self.send("/info"))
        self.assertFalse(self.feature.sessions)
        await self.ready()
        next(iter(self.feature.sessions.values())).expires = 0
        self.assertIn("超时", await self.send(FITTING))
        self.assertFalse(self.feature.sessions)
        self.client.import_fitting.assert_not_called()

    async def test_invalid_input_and_api_failure(self):
        await self.send("/fitt", start=True)
        self.assertIn("有效的角色名", await self.send("bad\nname"))
        await self.send("角色名")
        self.assertIn("格式无效", await self.send("hello"))
        self.client.import_fitting.side_effect = FittingImportError("角色未授权")
        self.assertIn("配置导入失败：角色未授权", await self.send(FITTING))
        self.assertFalse(self.feature.sessions)

    async def test_timeout_does_not_retry(self):
        await self.ready()
        self.client.import_fitting.side_effect = requests.Timeout()
        self.assertIn("结果待确认", await self.send(FITTING))
        self.client.import_fitting.assert_called_once()
        self.assertFalse(self.feature.pending)

    async def test_concurrent_messages_during_submission(self):
        await self.ready()
        gate = asyncio.Event()

        async def submit(*args):
            await gate.wait()

        with patch("plugin.features.fitting.service.asyncio.to_thread", side_effect=submit):
            task = asyncio.create_task(self.send(FITTING))
            await asyncio.sleep(0)
            self.assertIn("正在导入", await self.send(FITTING))
            self.assertIn("正在导入", await self.send("/fitt", start=True))
            gate.set()
            self.assertIn("导入成功", await task)


class FittingClientTests(unittest.TestCase):
    @patch("plugin.features.fitting.client.requests.post")
    def test_json_contract(self, post):
        post.return_value = Mock(status_code=200, json=lambda: {"code": 0, "data": {}})
        FittingClient().import_fitting("1718018032", "角色名", FITTING)
        post.assert_called_once_with(
            "https://admin-api.oofo.cc/game/eve/public/users/by-qq/1718018032/fittings",
            json={"characterName": "角色名", "fittingText": FITTING},
            timeout=20,
            allow_redirects=False,
        )

    @patch("plugin.features.fitting.client.requests.post")
    def test_http_business_and_malformed_errors(self, post):
        for status, payload in [
            (400, {"code": 0}),
            (200, {"code": 46104}),
            (200, {}),
            (200, []),
            (302, {"code": 0}),
        ]:
            post.return_value = Mock(status_code=status, json=lambda: payload)
            with self.assertRaises(FittingImportError):
                FittingClient().import_fitting("1718018032", "角色名", FITTING)
        post.return_value = Mock(status_code=502)
        post.return_value.json.side_effect = ValueError()
        with self.assertRaises(FittingImportError):
            FittingClient().import_fitting("1718018032", "角色名", FITTING)
