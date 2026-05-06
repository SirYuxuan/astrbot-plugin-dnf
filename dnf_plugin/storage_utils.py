import json
import os
from typing import Any

from astrbot.api import logger


class JsonFileStore:
    """Small JSON persistence helper for plugin runtime state."""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir

    def path(self, filename: str) -> str:
        return os.path.join(self.base_dir, filename)

    def load(self, filename: str, default: Any) -> Any:
        file_path = self.path(filename)
        if not os.path.exists(file_path):
            return default
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取状态文件失败 {filename}: {e}")
            return default

    def save(self, filename: str, data: Any) -> None:
        file_path = self.path(filename)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存状态文件失败 {filename}: {e}")
