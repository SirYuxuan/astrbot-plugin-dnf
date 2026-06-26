from ..config import PluginConfig
from ..storage_utils import JsonFileStore


class FeatureBase:
    """所有 Feature 的公共基类，持有 config / store / context。"""

    def __init__(self, config: PluginConfig, store: JsonFileStore, context) -> None:
        self.config = config
        self.store = store
        self.context = context

    def _get_aiocqhttp_client(self):
        platform_name = self.config.get("platform.name", "aiocqhttp")
        for platform in self.context.platform_manager.get_insts():
            if platform.meta().name == platform_name:
                return platform.get_client()
        return None
