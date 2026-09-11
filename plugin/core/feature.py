from .config import PluginConfig
from .notifications import GroupNotifier
from .storage import JsonFileStore


class MonitorFeature:
    """监控功能共用的依赖；平台选择与任务生命周期不属于业务逻辑。"""

    name: str

    def __init__(self, config: PluginConfig, store: JsonFileStore, notifier: GroupNotifier):
        self.config = config
        self.store = store
        self.notifier = notifier

    @property
    def enabled(self) -> bool:
        return bool(self.config.get(f"{self.name}.monitor_enabled", True))

    async def notify(self, message: str) -> bool:
        return await self.notifier.send_group(
            int(self.config.get(f"{self.name}.notify_group_id")), message
        )
