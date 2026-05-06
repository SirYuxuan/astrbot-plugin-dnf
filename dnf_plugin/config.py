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
    "image_ai": {
        "enabled": False,
        "endpoint": "",
        "api_key": "",
        "auth_header": "api-key",
        "size": "1024x1024",
        "quality": "low",
        "output_format": "png",
        "timeout_seconds": 180,
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

    def section(self, name: str) -> dict:
        value = self._config.get(name, {})
        return value if isinstance(value, dict) else {}

    def _merge(self, target: dict, source: dict) -> None:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                self._merge(target[key], value)
            else:
                target[key] = value

    def _to_plain_dict(self, value: Any) -> dict:
        if isinstance(value, dict):
            return value
        if hasattr(value, "data") and isinstance(value.data, dict):
            return value.data
        if hasattr(value, "to_dict"):
            data = value.to_dict()
            return data if isinstance(data, dict) else {}
        return {}
