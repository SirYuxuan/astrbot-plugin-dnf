"""组合根：只在这里装配功能及共享依赖，不负责框架事件处理。"""

from .core.config import PluginConfig
from .core.notifications import GroupNotifier
from .core.runtime import FeatureRuntime
from .core.storage import JsonFileStore
from .features.egg.service import EggFeature
from .features.gold.service import GoldFeature
from .features.oil.service import OilFeature


class PluginApplication:
    def __init__(self, config: PluginConfig, store: JsonFileStore, notifier: GroupNotifier):
        self.gold = GoldFeature(config, store, notifier)
        self.oil = OilFeature(config, store, notifier)
        self.egg = EggFeature(config, store, notifier)
        self.runtime = FeatureRuntime((self.gold, self.oil, self.egg))
