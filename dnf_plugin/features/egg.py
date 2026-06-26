import asyncio
import datetime

from astrbot.api import logger

from ..egg_utils import fetch_egg_prices, format_egg_items, format_egg_prices, parse_egg_args
from .base import FeatureBase


class EggFeature(FeatureBase):
    def __init__(self, config, store, context) -> None:
        super().__init__(config, store, context)
        self._task: asyncio.Task | None = None
        raw = self.store.load("last_egg_sent_date.json", {})
        self.last_egg_sent_date: str | None = raw.get("last_egg_sent_date") if isinstance(raw, dict) else None

    def start(self) -> None:
        if self.config.get("egg.monitor_enabled", True):
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def query(self, message: str) -> str:
        area, date_str = parse_egg_args(message)
        return await asyncio.to_thread(
            format_egg_prices,
            area,
            date_str,
            int(self.config.get("egg.daily_limit", 10)),
        )

    async def _loop(self) -> None:
        await asyncio.sleep(2)
        while True:
            try:
                today = datetime.date.today().strftime("%Y-%m-%d")
                if self.last_egg_sent_date != today:
                    await self._send_daily_notice(today)
                await asyncio.sleep(max(60, int(self.config.get("egg.interval_seconds", 3600))))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"蛋价任务异常: {e}")
                await asyncio.sleep(60)

    async def _send_daily_notice(self, today: str) -> None:
        date_str = datetime.date.today().strftime("%Y%m%d")
        items = await asyncio.to_thread(
            fetch_egg_prices,
            str(self.config.get("egg.monitor_area", "平舆")),
            date_str,
        )
        if not items:
            return
        message = format_egg_items(
            items, [], datetime.date.today(),
            limit=int(self.config.get("egg.daily_limit", 10)),
        )
        client = self._get_aiocqhttp_client()
        if not client:
            return
        await client.send_group_msg(
            group_id=int(self.config.get("egg.notify_group_id", 527189909)),
            message=message,
        )
        self.last_egg_sent_date = today
        self.store.save("last_egg_sent_date.json", {"last_egg_sent_date": today})
