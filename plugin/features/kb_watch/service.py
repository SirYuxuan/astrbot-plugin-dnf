from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
from typing import Any

import requests

from ...core.feature import MonitorFeature
from ..eve.catalog import EveCatalog
from .client import ZkillLiveClient
from .formatter import KbWatchFormatter

logger = logging.getLogger(__name__)


class KbWatchFeature(MonitorFeature):
    name = "kb_watch"

    def __init__(self, config, store, notifier, client: ZkillLiveClient, catalog: EveCatalog):
        super().__init__(config, store, notifier)
        self.client = client
        self.catalog = catalog
        raw = self.store.load("kb_watch_state.json", {})
        self.state: dict[str, Any] = raw if isinstance(raw, dict) else {}
        if "subscriber_qq_ids" not in self.state:
            configured = self.config.get("kb_watch.subscriber_qq_ids", [])
            subscribers = configured if isinstance(configured, list) else []
            self.state["subscriber_qq_ids"] = self._valid_subscribers(subscribers)
            self._save_state()
        if "alliance_session_origins" not in self.state:
            self.state["alliance_session_origins"] = []
            self._save_state()

    @property
    def corporation_id(self) -> int:
        return int(self.config.get("kb_watch.corporation_id", 0))

    @property
    def alliance_id(self) -> int:
        return int(self.config.get("kb_watch.alliance_id", 0))

    @property
    def subscribers(self) -> list[int]:
        return self._valid_subscribers(self.state.get("subscriber_qq_ids", []))

    @property
    def alliance_sessions(self) -> list[str]:
        value = self.state.get("alliance_session_origins", [])
        if not isinstance(value, list):
            return []
        return sorted({str(item).strip() for item in value if str(item).strip()})

    async def toggle(self, qq: str, *, is_group: bool) -> str:
        if not is_group:
            return "请在群聊中使用 /subkb"
        qq = qq.strip()
        if not re.fullmatch(r"[1-9]\d{4,11}", qq):
            return "无法获取有效的用户 QQ"
        user_id = int(qq)
        subscribers = self.subscribers
        if user_id in subscribers:
            subscribers.remove(user_id)
            self.state["subscriber_qq_ids"] = subscribers
            self._save_state()
            return "已取消军团 KB 私聊订阅。"
        subscribers.append(user_id)
        self.state["subscriber_qq_ids"] = sorted(set(subscribers))
        self._save_state()
        return "军团 KB 订阅成功，记录将推送至 QQ 私聊，请先添加机器人好友。"

    async def toggle_alliance(self, session: str, *, platform_name: str, is_group: bool) -> str:
        if platform_name.casefold() != "kook":
            return "请在 KOOK 频道中使用 /suballkb"
        if not is_group:
            return "请在 KOOK 频道中使用 /suballkb"
        session = session.strip()
        if not session:
            return "无法获取当前 KOOK 频道会话"
        sessions = self.alliance_sessions
        if session in sessions:
            sessions.remove(session)
            self.state["alliance_session_origins"] = sessions
            self._save_state()
            return "已取消当前 KOOK 频道的联盟 KB 订阅。"
        sessions.append(session)
        self.state["alliance_session_origins"] = sorted(set(sessions))
        self._save_state()
        return "联盟 KB 订阅成功，击杀和损失将推送至当前 KOOK 频道。"

    async def run(self) -> None:
        await self._send_startup_test()
        while True:
            try:
                has_corporation_target = bool(self.subscribers) and self.corporation_id > 0
                has_alliance_target = bool(self.alliance_sessions) and self.alliance_id > 0
                if not has_corporation_target and not has_alliance_target:
                    await asyncio.sleep(30)
                    continue
                if not self.state.get("next_sequence"):
                    latest = await asyncio.to_thread(self.client.latest_sequence)
                    self.state["next_sequence"] = latest + 1
                    self._save_state()
                    await asyncio.sleep(6)
                    continue
                sequence = int(self.state["next_sequence"])
                package = await asyncio.to_thread(self.client.package, sequence)
                if package is None:
                    await self._handle_missing_sequence(sequence)
                    continue
                await self._process_package(package)
                self.state["next_sequence"] = sequence + 1
                self._save_state()
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                raise
            except (requests.RequestException, ValueError, TypeError):
                logger.exception("zKillboard 军团订阅数据读取失败")
                await asyncio.sleep(6)
            except Exception:
                logger.exception("zKillboard 军团订阅任务异常")
                await asyncio.sleep(6)

    async def _send_startup_test(self) -> None:
        if not self.config.get("kb_watch.startup_test_enabled", True):
            return
        sessions = self.alliance_sessions
        if not sessions:
            return
        package = {
            "killmail_id": 139000000,
            "esi": {
                "killmail_time": dt.datetime.now(dt.timezone.utc).isoformat(),
                "solar_system_id": 30000142,
                "victim": {
                    "character_id": 2124718609,
                    "corporation_id": 98828269,
                    "alliance_id": 99007887,
                    "ship_type_id": 17715,
                },
                "attackers": [
                    {
                        "character_id": 2124698588,
                        "corporation_id": 98828269,
                        "alliance_id": 99007887,
                        "final_blow": True,
                    }
                ],
            },
            "zkb": {"totalValue": 1_250_000_000},
        }
        names = {
            2124698588: "Yuxan Axiom",
            2124718609: "Yuxan Hauler",
            98828269: "The Ninth Person",
            99007887: "Brotherhood of Spacers",
            30000142: "Jita",
        }
        card = self._formatter().format_card(
            package,
            "联盟 KB 测试消息",
            names_override=names,
            ship_name_override="毒蜥级",
            detail_url_override="https://zkillboard.com/alliance/99007887/",
        )
        fallback = "【联盟 KB 测试消息】\n插件已加载，KOOK 联盟 KB 卡片推送正常。"
        for session in sessions:
            try:
                sent = await self.notifier.send_session_card(session, card)
                if not sent:
                    await self.notifier.send_session(session, fallback)
            except Exception:
                logger.exception("KOOK 启动测试卡片发送失败，尝试文字降级: session=%s", session)
                try:
                    await self.notifier.send_session(session, fallback)
                except Exception:
                    logger.exception("KOOK 启动测试文字发送失败: session=%s", session)

    async def _handle_missing_sequence(self, sequence: int) -> None:
        latest = await asyncio.to_thread(self.client.latest_sequence)
        if latest > sequence:
            self.state["next_sequence"] = latest + 1
            self._save_state()
        await asyncio.sleep(6)

    async def _process_package(self, package: dict[str, Any]) -> None:
        killmail_id = self._integer(package.get("killmail_id"))
        if killmail_id <= 0 or killmail_id in self._seen_ids():
            return
        corporation_event = self._event_type(package)
        alliance_event = self._alliance_event_type(package)
        matched = False
        if corporation_event and self.subscribers:
            matched = True
            message = await asyncio.to_thread(
                self._formatter().format_text, package, corporation_event
            )
            for user_id in self.subscribers:
                try:
                    sent = await self.notifier.send_private(user_id, message)
                    if not sent:
                        logger.warning("KB 私聊推送平台不可用: qq=%s", user_id)
                except Exception:
                    logger.exception("KB 私聊推送失败: qq=%s", user_id)
        if alliance_event and self.alliance_sessions:
            matched = True
            card = await asyncio.to_thread(self._formatter().format_card, package, alliance_event)
            fallback = None
            for session in self.alliance_sessions:
                try:
                    sent = await self.notifier.send_session_card(session, card)
                    if not sent:
                        if fallback is None:
                            fallback = await asyncio.to_thread(
                                self._formatter().format_text, package, alliance_event
                            )
                        sent = await self.notifier.send_session(session, fallback)
                    if not sent:
                        logger.warning("联盟 KB KOOK 推送平台不可用: session=%s", session)
                except Exception:
                    logger.exception("联盟 KB KOOK 卡片推送失败，尝试文字降级: session=%s", session)
                    try:
                        if fallback is None:
                            fallback = await asyncio.to_thread(
                                self._formatter().format_text, package, alliance_event
                            )
                        await self.notifier.send_session(session, fallback)
                    except Exception:
                        logger.exception("联盟 KB KOOK 文字推送失败: session=%s", session)
        if not matched:
            return
        seen = (self._seen_ids() + [killmail_id])[-500:]
        self.state["seen_killmail_ids"] = seen
        self._save_state()

    def _event_type(self, package: dict[str, Any]) -> str | None:
        return self._event_type_for(
            package, entity_key="corporation_id", entity_id=self.corporation_id, label="军团"
        )

    def _alliance_event_type(self, package: dict[str, Any]) -> str | None:
        return self._event_type_for(
            package, entity_key="alliance_id", entity_id=self.alliance_id, label="联盟"
        )

    def _event_type_for(
        self, package: dict[str, Any], *, entity_key: str, entity_id: int, label: str
    ) -> str | None:
        if entity_id <= 0:
            return None
        esi = package.get("esi")
        if not isinstance(esi, dict):
            return None
        victim = esi.get("victim") if isinstance(esi.get("victim"), dict) else {}
        attackers = esi.get("attackers") if isinstance(esi.get("attackers"), list) else []
        is_loss = self._integer(victim.get(entity_key)) == entity_id
        is_kill = any(
            isinstance(attacker, dict) and self._integer(attacker.get(entity_key)) == entity_id
            for attacker in attackers
        )
        if is_loss and is_kill:
            return f"{label}内部损失"
        if is_loss:
            return f"{label} KB 损失"
        if is_kill:
            return f"{label} KB 击杀"
        return None

    def _formatter(self) -> KbWatchFormatter:
        return KbWatchFormatter(self.client, self.catalog)

    def _seen_ids(self) -> list[int]:
        value = self.state.get("seen_killmail_ids", [])
        if not isinstance(value, list):
            return []
        return [item for item in (self._integer(raw) for raw in value) if item > 0]

    def _save_state(self) -> None:
        self.store.save("kb_watch_state.json", self.state)

    @staticmethod
    def _valid_subscribers(values: Any) -> list[int]:
        if not isinstance(values, list):
            return []
        result = []
        for value in values:
            text = str(value).strip()
            if re.fullmatch(r"[1-9]\d{4,11}", text):
                result.append(int(text))
        return sorted(set(result))

    @staticmethod
    def _integer(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
