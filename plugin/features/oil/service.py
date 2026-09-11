import asyncio
import datetime
import logging
import re

from ...core.feature import MonitorFeature
from .client import (
    calculate_oil_cost,
    fetch_oil_data,
    format_oil_info,
    get_oil_price_by_type,
    has_oil_price_changed,
)

logger = logging.getLogger(__name__)


class OilFeature(MonitorFeature):
    name = "oil"

    def __init__(self, config, store, notifier) -> None:
        super().__init__(config, store, notifier)
        raw = self.store.load("last_oil_data.json", {})
        self.last_oil_data: dict = raw if isinstance(raw, dict) else {}

    async def query(self, message: str) -> str:
        message = message.strip()
        calc_match = re.fullmatch(r"/?油价\s+(\S+)\s+(\d+)\s+(\d+(?:\.\d+)?)(?:\s+(\d+))?", message)
        if calc_match:
            area = calc_match.group(1)
            oil_type = calc_match.group(2)
            consumption = float(calc_match.group(3))
            distance = int(calc_match.group(4)) if calc_match.group(4) else 100
            if consumption <= 0 or distance <= 0:
                return "❌ 油耗和里程必须大于 0"
            oil_data = await asyncio.to_thread(fetch_oil_data, area)
            oil_price = get_oil_price_by_type(oil_data or {}, oil_type)
            if oil_price is None:
                return f"❌ 无法获取{area}地区{oil_type}号油的价格信息"
            return calculate_oil_cost(oil_type, oil_price, consumption, distance, area)

        area_match = re.fullmatch(r"/?油价\s+([^\s\d]+)", message)
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

    async def run(self) -> None:
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
        await self._collect_and_notify(only_changes=False)

    async def _check_and_send_changes(self) -> None:
        await self._collect_and_notify(only_changes=True)

    async def _collect_and_notify(self, *, only_changes: bool) -> None:
        next_data = dict(self.last_oil_data)
        infos = []
        for area in self._configured_areas():
            oil = await asyncio.to_thread(fetch_oil_data, area)
            if not oil:
                continue
            if not only_changes or has_oil_price_changed(self.last_oil_data.get(area), oil):
                infos.append(format_oil_info(oil))
                next_data[area] = oil
        # 平台未连接或发送失败时不推进快照，下次仍然能够检测到变化。
        if infos and await self.notify("油价更新通知：\n\n" + "\n".join(infos)):
            self.store.save("last_oil_data.json", next_data)
            self.last_oil_data = next_data
