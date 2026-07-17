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
        "text_provider": "microsoft",
        "edit_provider": "microsoft",
        "microsoft_endpoint": "",
        "microsoft_edit_endpoint": "",
        "microsoft_api_key": "",
        "microsoft_auth_header": "api-key",
        "model": "",
        "size": "1024x1024",
        "quality": "medium",
        "output_format": "jpeg",
        "output_compression": 100,
        "num_images": 1,
        "edit_prompt_prefix": "Please edit the provided image according to the user's request. Keep the content safe and non-sensitive. User request: ",
        "fal_text_endpoint": "",
        "fal_edit_endpoint": "",
        "fal_key": "",
        "fal_poll_interval_seconds": 2,
        "fal_timeout_seconds": 180,
        "timeout_seconds": 180,
    },
    "music_ai": {
        "enabled": False,
        "endpoint": "https://queue.fal.run/fal-ai/minimax-music/v2.6",
        "api_key": "",
        "timeout_seconds": 180,
        "poll_interval_seconds": 2,
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

    def set(self, path: str, value: Any) -> None:
        current = self._config
        parts = path.split(".")
        for part in parts[:-1]:
            if not isinstance(current.get(part), dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

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
