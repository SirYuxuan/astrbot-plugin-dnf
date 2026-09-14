from copy import deepcopy
from typing import Any

DEFAULT_CONFIG = {
    "platform": {
        "name": "aiocqhttp",
    },
    "gold": {
        "monitor_enabled": True,
        "notify_group_id": 101344113,
        "interval_seconds": 60,
        "change_threshold": 2.0,
    },
    "oil": {
        "monitor_enabled": True,
        "notify_group_id": 101344113,
        "monitor_areas": ["河南"],
        "check_hour": 8,
        "startup_notice_enabled": True,
    },
    "egg": {
        "monitor_enabled": True,
        "notify_group_id": 527189909,
        "monitor_area": "平舆",
        "interval_seconds": 3600,
        "daily_limit": 10,
    },
    "eve": {
        "search_result_limit": 5,
        "request_timeout_seconds": 30,
        "sde_timeout_seconds": 300,
        "cache_seconds": 300,
        "cache_stale_seconds": 43200,
        "history_cache_seconds": 21600,
        "history_request_timeout_seconds": 30,
        "adam4eve_history_url": "https://www.adam4eve.eu/hub_type_history.php",
        "fuzzwork_url": "https://market.fuzzwork.co.uk/aggregates/",
        "redis_url": "redis://localhost:6379/0",
        "redis_prefix": "yuxuandnf:eve",
        "user_agent": "astrbot-plugin-dnf/1.6 (+https://github.com/SirYuxuan/astrbot-plugin-dnf)",
    },
}


class PluginConfig:
    def __init__(self, raw_config: Any = None):
        self._config = deepcopy(DEFAULT_CONFIG)
        if raw_config:
            self._merge(self._config, self._to_plain_dict(raw_config))

    def get(self, path: str, default: Any = None) -> Any:
        current = self._config
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def _merge(self, target: dict, source: dict) -> None:
        for key, value in source.items():
            if key not in target:
                continue
            if isinstance(target.get(key), dict):
                if isinstance(value, dict):
                    self._merge(target[key], value)
            else:
                target[key] = deepcopy(value)

    def _to_plain_dict(self, value: Any) -> dict:
        if isinstance(value, dict):
            return value
        if hasattr(value, "data") and isinstance(value.data, dict):
            return value.data
        if hasattr(value, "to_dict"):
            data = value.to_dict()
            return data if isinstance(data, dict) else {}
        return {}
