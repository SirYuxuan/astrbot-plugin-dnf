from ...core.config import PluginConfig


class AstrBotGroupNotifier:
    """保留现有群推送行为；未来增加平台只需替换这个适配器。"""

    def __init__(self, context, config: PluginConfig):
        self._context = context
        self._config = config

    async def send_group(self, group_id: int, message: str) -> bool:
        platform_name = self._config.get("platform.name", "aiocqhttp")
        for platform in self._context.platform_manager.get_insts():
            if platform.meta().name == platform_name:
                client = platform.get_client()
                if client is None:
                    return False
                await client.send_group_msg(group_id=group_id, message=message)
                return True
        return False
