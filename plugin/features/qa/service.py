"""持久化精确匹配问答，保留答案中的空格和换行。"""

import re

from ...core.storage import JsonFileStore


class QaFeature:
    FILENAME = "qa_entries.json"
    USAGE = '用法：/add .xx 解答内容\n关键词含空格：/add ".xx xx" 解答内容'

    def __init__(self, store: JsonFileStore):
        self.store = store
        entries = store.load(self.FILENAME, {})
        self.entries = (
            {key: value for key, value in entries.items() if isinstance(value, str)}
            if isinstance(entries, dict)
            else {}
        )

    @staticmethod
    def _key(text: str) -> str:
        return " ".join(text.split())

    async def add(self, message: str) -> str:
        # Strip the command only; answer text must not go through shlex/split.
        command = re.match(r"^\S+\s+(.+)$", message.strip(), re.DOTALL)
        if not command:
            return self.USAGE
        match = re.match(
            r"""^(?:"([^"]+)"|'([^']+)'|(\S+))\s+(.+)$""",
            command[1],
            re.DOTALL,
        )
        if not match:
            return self.USAGE
        key = self._key(next(part for part in match.groups()[:3] if part is not None))
        answer = match[4].strip()
        if not key.startswith(".") or key == "." or not answer:
            return self.USAGE
        entries = {**self.entries, key: answer}
        updated = key in self.entries
        self.store.save(self.FILENAME, entries)
        self.entries = entries
        return f"已{'更新' if updated else '添加'}问答：{key}"

    def answer(self, message: str) -> str | None:
        return self.entries.get(self._key(message))
