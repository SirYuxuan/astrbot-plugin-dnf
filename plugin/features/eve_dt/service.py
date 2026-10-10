from __future__ import annotations

import asyncio
import datetime as dt
import logging

import requests

from ...core.feature import MonitorFeature
from .client import EveServerStatus, EveStatusClient

logger = logging.getLogger(__name__)


class EveDowntimeFeature(MonitorFeature):
    name = "eve_dt"
    WARNING_MESSAGE = "5分钟后游戏DT。"
    ONLINE_MESSAGE = "游戏已经开服！！！"
    _BEIJING = dt.timezone(dt.timedelta(hours=8))
    _UTC = dt.timezone.utc

    def __init__(self, config, store, notifier, client: EveStatusClient) -> None:
        super().__init__(config, store, notifier)
        self.client = client
        raw = self.store.load("eve_dt_state.json", {})
        self.state: dict[str, str] = raw if isinstance(raw, dict) else {}

    async def query(self) -> str:
        try:
            status = await asyncio.to_thread(self.client.status)
        except (requests.RequestException, ValueError):
            logger.exception("查询 EVE 服务器状态失败")
            return "EVE服务器状态查询失败，请稍后重试"
        if status.vip:
            state = "维护中（VIP模式）"
        elif status.players > 0:
            state = "已开服"
        else:
            state = "维护中"
        return f"EVE服务器状态：{state}\n当前在线：{status.players:,} 人"

    async def run(self) -> None:
        while True:
            try:
                now = dt.datetime.now(self._BEIJING)
                sleep_seconds = await self._tick(now)
                await asyncio.sleep(sleep_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("EVE DT 监控任务异常")
                await asyncio.sleep(60)

    async def _tick(self, now: dt.datetime) -> float:
        now = now.astimezone(self._BEIJING)
        today = now.date().isoformat()
        warning_at = now.replace(hour=18, minute=55, second=0, microsecond=0)
        downtime_at = now.replace(hour=19, minute=0, second=0, microsecond=0)

        if warning_at <= now < downtime_at and self.state.get("active_date") != today:
            await self._start_cycle(today)

        if now < downtime_at and self.state.get("active_date") == today:
            return max(1.0, (downtime_at - now).total_seconds())

        if (
            now >= downtime_at
            and self.state.get("active_date") == today
            and self.state.get("online_sent_date") != today
        ):
            await self._check_online(today, downtime_at.astimezone(self._UTC))
            if self.state.get("online_sent_date") != today:
                return max(10, int(self.config.get("eve_dt.poll_interval_seconds", 30)))

        next_warning = warning_at
        if now >= warning_at:
            next_warning += dt.timedelta(days=1)
        return max(1.0, (next_warning - now).total_seconds())

    async def _start_cycle(self, today: str) -> None:
        self._update_state(active_date=today)
        if await self.notify(self.WARNING_MESSAGE):
            self._update_state(warning_sent_date=today)

    async def _check_online(self, today: str, downtime_at_utc: dt.datetime) -> None:
        try:
            status = await asyncio.to_thread(self.client.status)
        except (requests.RequestException, ValueError):
            logger.info("EVE 尚未开服或 ESI 状态暂不可用")
            return
        if not self.is_online_after_downtime(status, downtime_at_utc):
            return
        if await self.notify(self.ONLINE_MESSAGE):
            self._update_state(online_sent_date=today)

    @staticmethod
    def is_online_after_downtime(status: EveServerStatus, downtime_at_utc: dt.datetime) -> bool:
        return (
            status.players > 0
            and not status.vip
            and status.start_time.astimezone(dt.timezone.utc) >= downtime_at_utc
        )

    def _update_state(self, **values: str) -> None:
        next_state = {**self.state, **values}
        self.store.save("eve_dt_state.json", next_state)
        self.state = next_state
