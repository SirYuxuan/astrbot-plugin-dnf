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
from .features.eve_dt.client import EveStatusClient
from .features.eve_dt.service import EveDowntimeFeature
from .features.gold.service import GoldFeature
from .features.help.service import HelpFeature
from .features.info.client import InfoClient
from .features.info.service import InfoFeature
from .features.kb.client import KbClient
from .features.kb.service import KbFeature
from .features.kb_watch.client import ZkillLiveClient
from .features.kb_watch.service import KbWatchFeature
from .features.oil.service import OilFeature
from .features.rat.client import RatClient
from .features.rat.service import RatFeature
from .features.ship.client import ShipClient
from .features.ship.renderer import ShipCardRenderer
from .features.ship.service import ShipFeature
from .features.ship_training.service import ShipTrainingFeature
from .features.timer.service import TimerFeature
from .features.translate.client import TranslateClient
from .features.translate.service import TranslateFeature


class PluginApplication:
    def __init__(self, config: PluginConfig, store: JsonFileStore, notifier: GroupNotifier):
        self.gold = GoldFeature(config, store, notifier)
        self.help = HelpFeature()
        self.oil = OilFeature(config, store, notifier)
        self.egg = EggFeature(config, store, notifier)
        self.rat = RatFeature(
            RatClient(
                url=str(config.get("rat.url", RatClient.DEFAULT_URL)),
                timeout=int(config.get("rat.request_timeout_seconds", 10)),
            )
        )
        self.info = InfoFeature(
            InfoClient(
                url=str(config.get("info.url", InfoClient.DEFAULT_URL)),
                timeout=int(config.get("info.request_timeout_seconds", 10)),
            )
        )
        self.translate = TranslateFeature(
            TranslateClient(
                url=str(config.get("translate.url", TranslateClient.DEFAULT_URL)),
                timeout=int(config.get("translate.request_timeout_seconds", 10)),
            )
        )
        self.timer = TimerFeature()
        self.ship = ShipFeature(
            ShipClient(
                info_url=str(config.get("ship.info_url", ShipClient.DEFAULT_INFO_URL)),
                image_url=str(config.get("ship.image_url", ShipClient.DEFAULT_IMAGE_URL)),
                timeout=int(config.get("ship.request_timeout_seconds", 15)),
            ),
            ShipCardRenderer(),
        )
        self.ship_training = ShipTrainingFeature(
            url=str(config.get("ship_training.url", ShipTrainingFeature.DEFAULT_URL)),
            timeout=int(config.get("ship_training.request_timeout_seconds", 15)),
        )
        self.kb = KbFeature(
            KbClient(
                timeout=int(config.get("kb.request_timeout_seconds", 15)),
                cache_seconds=int(config.get("kb.cache_seconds", 600)),
                user_agent=str(config.get("kb.user_agent", "astrbot-plugin-dnf/1.7")),
                esi_ids_url=str(config.get("kb.esi_ids_url", KbClient.ESI_IDS_URL)),
                esi_names_url=str(config.get("kb.esi_names_url", KbClient.ESI_NAMES_URL)),
                zkill_stats_url=str(config.get("kb.zkill_stats_url", KbClient.ZKILL_STATS_URL)),
            )
        )
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
        self.eve_dt = EveDowntimeFeature(
            config,
            store,
            notifier,
            EveStatusClient(
                url=str(config.get("eve_dt.status_url", EveStatusClient.DEFAULT_URL)),
                timeout=int(config.get("eve_dt.request_timeout_seconds", 10)),
                user_agent=str(config.get("eve_dt.user_agent", "astrbot-plugin-dnf/1.7")),
            ),
        )
        self.kb_watch = KbWatchFeature(
            config,
            store,
            notifier,
            ZkillLiveClient(
                timeout=int(config.get("kb_watch.request_timeout_seconds", 10)),
                user_agent=str(config.get("kb_watch.user_agent", "astrbot-plugin-dnf/1.7")),
                sequence_url=str(
                    config.get("kb_watch.sequence_url", ZkillLiveClient.DEFAULT_SEQUENCE_URL)
                ),
                ephemeral_url=str(
                    config.get("kb_watch.ephemeral_url", ZkillLiveClient.DEFAULT_EPHEMERAL_URL)
                ),
                names_url=str(config.get("kb_watch.names_url", ZkillLiveClient.DEFAULT_NAMES_URL)),
            ),
            catalog,
        )
        self.runtime = FeatureRuntime((self.gold, self.oil, self.egg, self.eve_dt, self.kb_watch))
