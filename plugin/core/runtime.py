"""所有后台任务由一个所有者管理，重复初始化不会重复启动。"""

import asyncio
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class BackgroundFeature(Protocol):
    name: str

    @property
    def enabled(self) -> bool: ...

    async def run(self) -> None: ...


class FeatureRuntime:
    def __init__(self, features: tuple[BackgroundFeature, ...]):
        names = [feature.name for feature in features]
        if len(names) != len(set(names)):
            raise ValueError("后台功能名称不能重复")
        self._features = features
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._lock:
            for feature in self._features:
                task = self._tasks.get(feature.name)
                if feature.enabled and (task is None or task.done()):
                    task = asyncio.create_task(feature.run(), name=f"plugin:{feature.name}")
                    task.add_done_callback(self._report_failure)
                    self._tasks[feature.name] = task

    @staticmethod
    def _report_failure(task: asyncio.Task) -> None:
        if not task.cancelled() and (error := task.exception()) is not None:
            logger.error("后台任务 %s 异常退出", task.get_name(), exc_info=error)

    async def stop(self) -> None:
        async with self._lock:
            tasks = list(self._tasks.values())
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self._tasks.clear()
