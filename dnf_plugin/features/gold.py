import asyncio
import re

from astrbot.api import logger

from ..dnf_utils import DnfGoldRatioFetcher
from .base import FeatureBase


class GoldFeature(FeatureBase):
    def __init__(self, config, store, context) -> None:
        super().__init__(config, store, context)
        self._task: asyncio.Task | None = None
        self.last_avg_ratio: float | None = self._load_float("last_avg_ratio.json", "last_avg_ratio")
        self.last_sent_avg_ratio: float | None = self._load_float("last_sent_avg_ratio.json", "last_sent_avg_ratio")

    def _load_float(self, filename: str, key: str) -> float | None:
        data = self.store.load(filename, {})
        if not isinstance(data, dict) or data.get(key) is None:
            return None
        try:
            return float(data[key])
        except Exception:
            logger.error(f"状态字段不是有效数字 {filename}:{key}")
            return None

    def start(self) -> None:
        if self.config.get("gold.monitor_enabled", True):
            self._task = asyncio.create_task(self._loop())
            logger.info("金币比例定时任务已启动，每分钟检测一次")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def query(self) -> str:
        return await asyncio.to_thread(DnfGoldRatioFetcher.fetch_gold_ratio_text)

    async def _loop(self) -> None:
        while True:
            try:
                client = self._get_aiocqhttp_client()
                if client:
                    ratio_text = await asyncio.to_thread(DnfGoldRatioFetcher.fetch_gold_ratio_text)
                    avg_ratio = self._parse_avg_ratio(ratio_text)
                    if avg_ratio is None:
                        logger.info("未能获取到金币均价数据")
                    else:
                        await self._maybe_send_notice(client, avg_ratio)
                        self.last_avg_ratio = avg_ratio
                        self.store.save("last_avg_ratio.json", {"last_avg_ratio": avg_ratio})
                await asyncio.sleep(max(10, int(self.config.get("gold.interval_seconds", 60))))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"金币比例定时任务执行失败: {e}")
                await asyncio.sleep(30)

    def _parse_avg_ratio(self, ratio_text: str) -> float | None:
        match = re.search(r"均价：1元=([\d.]+)万金币", ratio_text)
        return float(match.group(1)) if match else None

    async def _maybe_send_notice(self, client, avg_ratio: float) -> None:
        if self.last_sent_avg_ratio is None:
            message = f"首次监控，当前金币均价：{avg_ratio:.2f}万金币"
        else:
            diff = avg_ratio - self.last_sent_avg_ratio
            if abs(diff) < float(self.config.get("gold.change_threshold", 2.0)):
                return
            message = (
                f"金币比例波动：上次发送均价 {self.last_sent_avg_ratio:.2f}，"
                f"本次均价 {avg_ratio:.2f}，变动 {diff:+.2f}万金币"
            )
        await client.send_group_msg(
            group_id=int(self.config.get("gold.notify_group_id", 101344113)),
            message=message,
        )
        self.last_sent_avg_ratio = avg_ratio
        self.store.save("last_sent_avg_ratio.json", {"last_sent_avg_ratio": avg_ratio})
