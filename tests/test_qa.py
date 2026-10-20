"""问答解析、持久化及更新失败的回归验证。"""

import tempfile
import unittest
from unittest.mock import patch

from plugin.core.storage import JsonFileStore
from plugin.features.qa.service import QaFeature


class QaTests(unittest.IsolatedAsyncioTestCase):
    async def test_answers_preserve_whitespace_and_survive_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStore(directory)
            qa = QaFeature(store)
            self.assertIn("已添加", await qa.add("/add  .xx  解答  答\n第二行"))
            self.assertEqual(QaFeature(store).answer(" .xx "), "解答  答\n第二行")
            self.assertIsNone(qa.answer(".xx 其他内容"))
            self.assertIn("已更新", await qa.add("/add .xx 新答案"))
            self.assertEqual(QaFeature(store).answer(".xx"), "新答案")

    async def test_quoted_keys_and_invalid_input(self):
        with tempfile.TemporaryDirectory() as directory:
            qa = QaFeature(JsonFileStore(directory))
            await qa.add('add ".xx   xx" 答案包含 "引号" 和空格')
            self.assertEqual(qa.answer(" .xx\txx "), '答案包含 "引号" 和空格')
            await qa.add("/add '.另 一个' 第二个答案")
            self.assertEqual(qa.answer(".另 一个"), "第二个答案")
            for message in ("/add", "/add .xx", "/add xx 答案", '/add ".xx 答案', "/add . 答案"):
                self.assertEqual(await qa.add(message), qa.USAGE)
            self.assertEqual(len(qa.entries), 2)

    async def test_failed_write_does_not_replace_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStore(directory)
            qa = QaFeature(store)
            await qa.add("/add .xx 旧答案")
            with patch.object(store, "save", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    await qa.add("/add .xx 新答案")
            self.assertEqual(qa.answer(".xx"), "旧答案")
            self.assertEqual(QaFeature(store).answer(".xx"), "旧答案")
