"""原子 JSON 状态存储；可从旧插件目录惰性迁移状态。"""

import json
import logging
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class JsonFileStore:
    def __init__(self, base_dir: str | Path, legacy_dir: str | Path | None = None):
        self.base_dir = Path(base_dir)
        self.legacy_dir = Path(legacy_dir) if legacy_dir is not None else None
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def path(self, filename: str) -> Path:
        if not filename or Path(filename).name != filename or filename in (".", ".."):
            raise ValueError("状态文件名必须是简单文件名")
        return self.base_dir / filename

    def load(self, filename: str, default: Any) -> Any:
        path = self.path(filename)
        legacy = self.legacy_dir / filename if self.legacy_dir else None
        source = legacy if not path.exists() and legacy and legacy.is_file() else path
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return deepcopy(default)
        except (OSError, ValueError) as error:
            logger.warning("读取状态文件失败 %s: %s", source, error)
            return deepcopy(default)
        if source != path:
            self.save(filename, data)
        return data

    def save(self, filename: str, data: Any) -> None:
        """失败向调用者传播，避免把未持久化状态误认为已提交。"""
        path = self.path(filename)
        content = json.dumps(data, ensure_ascii=False)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.base_dir,
                prefix=f".{filename}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = stream.name
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
