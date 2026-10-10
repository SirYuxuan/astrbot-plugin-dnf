import asyncio
import logging
import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .client import EVE_BINDING_HINT, RatClient

logger = logging.getLogger(__name__)
SHANGHAI = ZoneInfo("Asia/Shanghai")


class RatFeature:
    def __init__(self, client: RatClient) -> None:
        self.client = client

    async def query(self, qq: str) -> str:
        qq = qq.strip()
        if not re.fullmatch(r"[1-9]\d{4,11}", qq):
            return "无法获取有效的用户 QQ"
        result = await asyncio.to_thread(self.client.query, qq)
        return result or "接口未返回内容"


class RatSubscriptionFeature:
    name = "rat_subscription"
    state_file = "rat_subscriptions.json"

    def __init__(self, config, store, notifier, rat: RatFeature) -> None:
        self.config = config
        self.store = store
        self.notifier = notifier
        self.rat = rat
        raw = store.load(self.state_file, {})
        state = raw if isinstance(raw, dict) else {}
        subscribers = state.get("subscribers", [])
        sent_dates = state.get("sent_dates", {})
        self.subscribers = (
            {str(qq) for qq in subscribers if re.fullmatch(r"[1-9]\d{4,11}", str(qq))}
            if isinstance(subscribers, list)
            else set()
        )
        self.sent_dates = (
            {
                str(qq): date
                for qq, date in sent_dates.items()
                if str(qq) in self.subscribers and isinstance(date, str)
            }
            if isinstance(sent_dates, dict)
            else {}
        )
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("rat.subscription_enabled", True))

    async def toggle(self, qq: str) -> str:
        qq = qq.strip()
        if not re.fullmatch(r"[1-9]\d{4,11}", qq):
            return "无法获取有效的用户 QQ"
        async with self._lock:
            subscribers = set(self.subscribers)
            sent_dates = dict(self.sent_dates)
            if qq in subscribers:
                subscribers.remove(qq)
                sent_dates.pop(qq, None)
                message = "已取消 RAT 每日私聊订阅。"
            else:
                subscribers.add(qq)
                message = (
                    "RAT 订阅成功，每天北京时间 23:50 推送至 QQ 私聊；"
                    "再次发送 /subrat 可取消。请先添加机器人好友。"
                )
            self._save(subscribers, sent_dates)
            self.subscribers = subscribers
            self.sent_dates = sent_dates
            return message

    async def run(self) -> None:
        while True:
            try:
                now = datetime.now(SHANGHAI)
                target = datetime.combine(now.date(), time(23, 50), SHANGHAI)
                if now >= target:
                    target += timedelta(days=1)
                await asyncio.sleep((target - now).total_seconds())
                await self.send_daily(target.date().isoformat())
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("RAT 每日订阅任务异常")
                await asyncio.sleep(60)

    async def send_daily(self, date: str) -> None:
        for qq in sorted(self.subscribers):
            async with self._lock:
                if qq not in self.subscribers or self.sent_dates.get(qq) == date:
                    continue
            try:
                report = await self.rat.query(qq)
                if not report or report in {EVE_BINDING_HINT, "接口未返回内容"}:
                    logger.warning("RAT 每日订阅无可发送数据: qq=%s", qq)
                    continue
                async with self._lock:
                    if qq not in self.subscribers or self.sent_dates.get(qq) == date:
                        continue
                    sent = await self.notifier.send_private(int(qq), report)
                    if not sent:
                        logger.warning("RAT 私聊推送平台不可用: qq=%s", qq)
                        continue
                    sent_dates = dict(self.sent_dates)
                    sent_dates[qq] = date
                    self._save(self.subscribers, sent_dates)
                    self.sent_dates = sent_dates
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("RAT 每日私聊推送失败: qq=%s", qq)

    def _save(self, subscribers: set[str], sent_dates: dict[str, str]) -> None:
        self.store.save(
            self.state_file,
            {"subscribers": sorted(subscribers), "sent_dates": sent_dates},
        )
