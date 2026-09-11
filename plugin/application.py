"""组合根：只在这里装配功能及共享依赖，不负责框架事件处理。"""

from .core.config import PluginConfig
from .core.notifications import GroupNotifier
from .core.runtime import FeatureRuntime
from .core.storage import JsonFileStore
from .features.egg.service import EggFeature
from .features.eve.catalog import EveCatalog
from .features.eve.client import EsiMarketClient, MemoryOrderCache, RedisOrderCache
from .features.eve.sde import SdeUpdater
from .features.eve.service import EveFeature
from .features.gold.service import GoldFeature
from .features.oil.service import OilFeature


class PluginApplication:
    def __init__(self, config: PluginConfig, store: JsonFileStore, notifier: GroupNotifier):
        self.gold = GoldFeature(config, store, notifier)
        self.oil = OilFeature(config, store, notifier)
        self.egg = EggFeature(config, store, notifier)
        eve_dir = store.base_dir / "eve"
        catalog = EveCatalog(eve_dir / "eve.db")
        redis_url = str(config.get("eve.redis_url", "") or "").strip()
        if redis_url:
            cache = RedisOrderCache(
                redis_url,
                prefix=str(config.get("eve.redis_prefix", "yuxuandnf:eve")),
                stale_seconds=int(config.get("eve.cache_stale_seconds", 3600)),
            )
        else:
            cache = MemoryOrderCache()
        user_agent = str(config.get("eve.user_agent", ""))
        market = EsiMarketClient(
            timeout=int(config.get("eve.request_timeout_seconds", 30)),
            cache_seconds=int(config.get("eve.cache_seconds", 300)),
            user_agent=user_agent,
            cache=cache,
        )
        updater = SdeUpdater(
            catalog,
            timeout=int(config.get("eve.sde_timeout_seconds", 300)),
            user_agent=user_agent,
        )
        self.eve = EveFeature(
            catalog,
            market,
            updater,
            search_result_limit=int(config.get("eve.search_result_limit", 5)),
        )
        self.runtime = FeatureRuntime((self.gold, self.oil, self.egg))
