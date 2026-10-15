from typing import Any

from ...core.config import PluginConfig


class AstrBotGroupNotifier:
    """保留现有群推送行为；未来增加平台只需替换这个适配器。"""

    def __init__(self, context, config: PluginConfig):
        self._context = context
        self._config = config

    async def send_group(self, group_id: int, message: str) -> bool:
        client = self._client()
        if client is None:
            return False
        await client.send_group_msg(group_id=group_id, message=message)
        return True

    async def send_private(self, user_id: int, message: str) -> bool:
        client = self._client()
        if client is None:
            return False
        await client.send_private_msg(user_id=user_id, message=message)
        return True

    async def send_private_image(self, user_id: int, path: str) -> bool:
        if not path.strip():
            return False
        from astrbot.api import message_components as Comp
        from astrbot.api.event import MessageChain

        chain = MessageChain()
        image = (
            Comp.Image.fromURL(path)
            if path.startswith(("http://", "https://", "data:"))
            else Comp.Image.fromFileSystem(path)
        )
        chain.chain.append(image)
        platform = str(self._config.get("platform.name", "aiocqhttp"))
        origin_platform = platform
        for instance in self._context.platform_manager.get_insts():
            try:
                if instance.meta().name == platform:
                    origin_platform = str(instance.meta().id)
                    break
            except AttributeError:
                continue
        return bool(
            await self._context.send_message(
                f"{origin_platform}:FriendMessage:{int(user_id)}", chain
            )
        )

    async def send_session(self, session: str, message: str) -> bool:
        if not session.strip():
            return False
        from astrbot.api.event import MessageChain

        return bool(await self._context.send_message(session, MessageChain().message(message)))

    async def send_session_card(self, session: str, card: dict[str, Any]) -> bool:
        if not session.strip():
            return False
        from astrbot.api import message_components as Comp
        from astrbot.api.event import MessageChain

        chain = MessageChain()
        chain.chain.append(Comp.Json(card))
        return bool(await self._context.send_message(session, chain))

    def _client(self):
        platform_name = self._config.get("platform.name", "aiocqhttp")
        for platform in self._context.platform_manager.get_insts():
            if platform.meta().name == platform_name:
                return platform.get_client()
        return None
