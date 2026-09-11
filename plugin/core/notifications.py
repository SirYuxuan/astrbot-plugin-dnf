from typing import Protocol


class GroupNotifier(Protocol):
    """发送成功返回 True；平台不可用返回 False；发送失败抛出异常。"""

    async def send_group(self, group_id: int, message: str) -> bool: ...
