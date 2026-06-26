import asyncio
import datetime
import re

from astrbot.api import logger

from ..oil_utils import (
    calculate_oil_cost,
    fetch_oil_data,
    format_oil_info,
    get_oil_price_by_type,
    has_oil_price_changed,
)
from .base import FeatureBase


class OilFeature(FeatureBase):
    def __init__(self, config, store, context) -> None:
        super().__init__(config, store, context)
        self._task: asyncio.Task | None = None
        raw = self.store.load("last_oil_data.json", {})
        self.last_oil_data: dict = raw if isinstance(raw, dict) else {}

    def start(self) -> None:
        if self.config.get("oil.monitor_enabled", True):
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
        calc_match = re.search(r"油价\s+([^\s]+)\s+(\d+)\s+([\d.]+)(?:\s+(\d+))?", message)
        if calc_match:
            area = calc_match.group(1)
            oil_type = calc_match.group(2)
            consumption = float(calc_match.group(3))
            distance = int(calc_match.group(4)) if calc_match.group(4) else 100
            oil_data = await asyncio.to_thread(fetch_oil_data, area)
            oil_price = get_oil_price_by_type(oil_data or {}, oil_type)
            if oil_price is None:
                return f"❌ 无法获取{area}地区{oil_type}号油的价格信息"
            return calculate_oil_cost(oil_type, oil_price, consumption, distance, area)

        area_match = re.search(r"油价\s+([^\s\d]+)$", message)
        if area_match:
            area = area_match.group(1).strip()
            oil_data = await asyncio.to_thread(fetch_oil_data, area)
            if oil_data:
                return format_oil_info(oil_data)
            return f"查询失败：未能获取{area}油价数据"

        return (
            "❌ 参数格式不正确\n\n"
            "📋 正确格式：\n"
            "• 油价 地区名 - 查询地区油价\n"
            "• 油价 地区名 油号 油耗 - 计算行驶成本\n"
            "• 油价 地区名 油号 油耗 里程 - 计算指定里程成本"
        )

    def _configured_areas(self) -> list[str]:
        areas = self.config.get("oil.monitor_areas", ["河南"])
        if not isinstance(areas, list):
            return ["河南"]
        return [str(a).strip() for a in areas if str(a).strip()]

    async def _loop(self) -> None:
        await asyncio.sleep(2)
        if self.config.get("oil.startup_notice_enabled", True):
            try:
                await self._send_startup_notice()
            except Exception as e:
                logger.error(f"发送启动时油价通知失败: {e}")
        while True:
            try:
                now = datetime.datetime.now()
                check_hour = min(23, max(0, int(self.config.get("oil.check_hour", 8))))
                target = now.replace(hour=check_hour, minute=0, second=0, microsecond=0)
                if now >= target:
                    target += datetime.timedelta(days=1)
                await asyncio.sleep((target - now).total_seconds())
                await self._check_and_send_changes()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"油价每日任务异常: {e}")
                await asyncio.sleep(60)

    async def _send_startup_notice(self) -> None:
        client = self._get_aiocqhttp_client()
        infos = []
        for area in self._configured_areas():
            oil = await asyncio.to_thread(fetch_oil_data, area)
            if oil:
                infos.append(format_oil_info(oil))
                self.last_oil_data[area] = oil
        if infos and client:
            await client.send_group_msg(
                group_id=int(self.config.get("oil.notify_group_id", 101344113)),
                message="油价更新通知：\n\n" + "\n".join(infos),
            )
        self.store.save("last_oil_data.json", self.last_oil_data)

    async def _check_and_send_changes(self) -> None:
        client = self._get_aiocqhttp_client()
        changed_infos = []
        for area in self._configured_areas():
            oil = await asyncio.to_thread(fetch_oil_data, area)
            if not oil:
                continue
            if has_oil_price_changed(self.last_oil_data.get(area), oil):
                changed_infos.append(format_oil_info(oil))
                self.last_oil_data[area] = oil
        if changed_infos and client:
            await client.send_group_msg(
                group_id=int(self.config.get("oil.notify_group_id", 101344113)),
                message="油价更新通知：\n\n" + "\n".join(changed_infos),
            )
        if changed_infos:
            self.store.save("last_oil_data.json", self.last_oil_data)
