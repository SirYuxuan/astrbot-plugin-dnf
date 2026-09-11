import asyncio
import datetime
import logging

from ...core.feature import MonitorFeature
from .client import fetch_egg_prices, format_egg_items, format_egg_prices, parse_egg_args

logger = logging.getLogger(__name__)


class EggFeature(MonitorFeature):
    name = "egg"

    def __init__(self, config, store, notifier) -> None:
        super().__init__(config, store, notifier)
        raw = self.store.load("last_egg_sent_date.json", {})
        self.last_egg_sent_date: str | None = (
            raw.get("last_egg_sent_date") if isinstance(raw, dict) else None
        )

    async def query(self, message: str) -> str:
        area, date_str = parse_egg_args(message)
        return await asyncio.to_thread(
            format_egg_prices,
            area,
            date_str,
            int(self.config.get("egg.daily_limit", 10)),
        )

    async def run(self) -> None:
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
        query_date = datetime.date.fromisoformat(today)
        date_str = query_date.strftime("%Y%m%d")
        items = await asyncio.to_thread(
            fetch_egg_prices,
            str(self.config.get("egg.monitor_area", "平舆")),
            date_str,
        )
        if not items:
            return
        message = format_egg_items(
            items,
            [],
            query_date,
            limit=int(self.config.get("egg.daily_limit", 10)),
        )
        if await self.notify(message):
            self.store.save("last_egg_sent_date.json", {"last_egg_sent_date": today})
            self.last_egg_sent_date = today
