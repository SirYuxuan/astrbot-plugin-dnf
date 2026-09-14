"""组合根：只在这里装配功能及共享依赖，不负责框架事件处理。"""

from .core.config import PluginConfig
from .core.notifications import GroupNotifier
from .core.runtime import FeatureRuntime
from .core.storage import JsonFileStore
from .features.egg.service import EggFeature
from .features.eve.catalog import EveCatalog
from .features.eve.chart import PriceChartRenderer
from .features.eve.client import (
    Adam4EveHistoryClient,
    EveMarketClient,
    FuzzworkMarketClient,
    MemoryOrderCache,
    RedisOrderCache,
)
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
                stale_seconds=int(config.get("eve.cache_stale_seconds", 43200)),
            )
        else:
            cache = MemoryOrderCache()
        user_agent = str(config.get("eve.user_agent", ""))
        current_market = FuzzworkMarketClient(
            timeout=int(config.get("eve.request_timeout_seconds", 30)),
            cache_seconds=int(config.get("eve.cache_seconds", 300)),
            user_agent=user_agent,
            cache=cache,
            url=str(
                config.get(
                    "eve.fuzzwork_url",
                    FuzzworkMarketClient.DEFAULT_URL,
                )
            ),
        )
        station_history = Adam4EveHistoryClient(
            timeout=int(config.get("eve.history_request_timeout_seconds", 30)),
            cache_seconds=int(config.get("eve.history_cache_seconds", 21600)),
            user_agent=user_agent,
            cache=cache,
            url=str(
                config.get(
                    "eve.adam4eve_history_url",
                    Adam4EveHistoryClient.DEFAULT_URL,
                )
            ),
        )
        market = EveMarketClient(
            current_market,
            station_history,
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
            chart_renderer=PriceChartRenderer(),
        )
        self.runtime = FeatureRuntime((self.gold, self.oil, self.egg))
