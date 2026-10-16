from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import requests

from ...core.feature import MonitorFeature
from ..eve.catalog import EveCatalog
from ..kb.renderer import KbKillmailRenderer
from .client import ZkillLiveClient
from .formatter import KbWatchFormatter

logger = logging.getLogger(__name__)


class KbWatchFeature(MonitorFeature):
    name = "kb_watch"
    YUXAN_LOSS_RECIPIENT = 1718018032

    def __init__(
        self,
        config,
        store,
        notifier,
        client: ZkillLiveClient,
        catalog: EveCatalog,
        *,
        renderer: KbKillmailRenderer | None = None,
    ):
        super().__init__(config, store, notifier)
        self.client = client
        self.catalog = catalog
        self.renderer = renderer or KbKillmailRenderer(client, catalog)
        self.html_renderer = None
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

    def set_html_renderer(self, renderer) -> None:
        self.html_renderer = renderer

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
        restricted_loss = await asyncio.to_thread(
            self._is_restricted_loss, package, corporation_event, alliance_event
        )
        matched = False
        private_event = (
            (corporation_event or alliance_event) if restricted_loss else corporation_event
        )
        recipients = [self.YUXAN_LOSS_RECIPIENT] if restricted_loss else self.subscribers
        if private_event and recipients:
            matched = True
            await self._send_private_record(package, private_event, recipients)
        if alliance_event and self.alliance_sessions and not restricted_loss:
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

    def _is_restricted_loss(
        self,
        package: dict[str, Any],
        corporation_event: str | None,
        alliance_event: str | None,
    ) -> bool:
        event_types = (corporation_event, alliance_event)
        if not any(event and "损失" in event for event in event_types):
            return False
        esi = package.get("esi")
        victim = esi.get("victim") if isinstance(esi, dict) else None
        if not isinstance(victim, dict):
            return False
        character_id = self._integer(victim.get("character_id"))
        if character_id <= 0:
            return False
        name = self.client.names([character_id]).get(character_id)
        if not name:
            raise ValueError(f"无法解析 KB 损失角色名: character_id={character_id}")
        return str(name).strip().casefold().startswith("yuxan")

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

    async def _send_private_record(
        self, package: dict[str, Any], event_type: str, recipients: list[int]
    ) -> None:
        rendered = ""
        if callable(self.html_renderer):
            try:
                markup = await asyncio.to_thread(self.renderer.render, package, event_type)
                rendered = await self.html_renderer(
                    markup,
                    {},
                    return_url=False,
                    options=self.renderer.image_render_options(markup),
                )
                rendered = str(rendered or "")
            except Exception:
                logger.exception("KB 图片通知渲染失败，降级为文字: event=%s", event_type)

        message: str | None = None
        for user_id in recipients:
            try:
                sent = False
                send_image = getattr(self.notifier, "send_private_image", None)
                if rendered and callable(send_image):
                    sent = await send_image(user_id, rendered)
                if not sent:
                    if message is None:
                        message = await asyncio.to_thread(
                            self._formatter().format_text, package, event_type
                        )
                    sent = await self.notifier.send_private(user_id, message)
                if not sent:
                    logger.warning("KB 私聊推送平台不可用: qq=%s", user_id)
            except Exception:
                logger.exception("KB 私聊推送失败: qq=%s", user_id)

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
