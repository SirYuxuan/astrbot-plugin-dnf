"""KB 战报文本与 KOOK 卡片格式化。"""

from __future__ import annotations

import datetime as dt
from typing import Any

from ..eve.catalog import EveCatalog
from .client import ZkillLiveClient


class KbWatchFormatter:
    _BEIJING = dt.timezone(dt.timedelta(hours=8))

    def __init__(self, client: ZkillLiveClient, catalog: EveCatalog):
        self.client = client
        self.catalog = catalog

    def format_text(self, package: dict[str, Any], event_type: str) -> str:
        esi = package["esi"]
        victim = esi.get("victim", {})
        character_id = self._integer(victim.get("character_id"))
        system_id = self._integer(esi.get("solar_system_id"))
        ship_type_id = self._integer(victim.get("ship_type_id"))
        names = self.client.names([character_id, system_id])
        character_name = names.get(character_id, "未知角色")
        system_name = names.get(system_id, f"星系 {system_id}" if system_id else "未知星系")
        ship = self.catalog.get_type(ship_type_id)
        ship_name = (ship.name_zh or ship.name_en) if ship else f"Type {ship_type_id}"
        zkb = package.get("zkb") if isinstance(package.get("zkb"), dict) else {}
        value = self._number(zkb.get("totalValue"))
        killmail_id = self._integer(package.get("killmail_id"))
        timestamp = self._parse_time(str(esi.get("killmail_time", "")))
        return (
            f"【{event_type}】\n"
            f"角色：{character_name}\n"
            f"舰船：{ship_name}\n"
            f"地点：{system_name}\n"
            f"价值：{self._format_isk(value)}\n"
            f"时间：{timestamp}\n"
            f"https://zkillboard.com/kill/{killmail_id}/"
        )

    def format_card(
        self,
        package: dict[str, Any],
        event_type: str,
        *,
        names_override: dict[int, str] | None = None,
        ship_name_override: str | None = None,
        detail_url_override: str | None = None,
    ) -> dict[str, Any]:
        esi = package["esi"]
        victim = esi.get("victim") if isinstance(esi.get("victim"), dict) else {}
        attackers = esi.get("attackers") if isinstance(esi.get("attackers"), list) else []
        attackers = [item for item in attackers if isinstance(item, dict)]
        final_blow = next((item for item in attackers if item.get("final_blow")), None)
        attacker = final_blow or (attackers[0] if attackers else {})

        victim_ids = self._identity_ids(victim)
        attacker_ids = self._identity_ids(attacker)
        system_id = self._integer(esi.get("solar_system_id"))
        names = (
            names_override
            if names_override is not None
            else self.client.names([*victim_ids.values(), *attacker_ids.values(), system_id])
        )

        victim_identity = self._identity(victim_ids, names, "未知目标")
        attacker_identity = self._identity(attacker_ids, names, "NPC / 未知角色")
        ship_type_id = self._integer(victim.get("ship_type_id"))
        ship = self.catalog.get_type(ship_type_id)
        ship_name = ship_name_override or (
            (ship.name_zh or ship.name_en) if ship else f"Type {ship_type_id}"
        )
        system_name = names.get(system_id, f"星系 {system_id}" if system_id else "未知星系")
        zkb = package.get("zkb") if isinstance(package.get("zkb"), dict) else {}
        value = self._number(zkb.get("totalValue"))
        killmail_id = self._integer(package.get("killmail_id"))
        detail_url = detail_url_override or f"https://zkillboard.com/kill/{killmail_id}/"
        timestamp = self._parse_time(str(esi.get("killmail_time", "")))
        theme, _ = self._card_style(event_type)

        ship_url = self._image_url("types", ship_type_id, "render", size=128)
        modules: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {"type": "plain-text", "content": event_type},
            },
            {
                "type": "section",
                "mode": "right",
                "text": self._kmarkdown(
                    f"**损失 {self._format_isk(value)}**\n{self._escape_kmarkdown(ship_name)}"
                ),
                **(
                    {"accessory": self._card_image(ship_url, ship_name, size="sm")}
                    if ship_url
                    else {}
                ),
            },
            {"type": "divider"},
        ]
        modules.extend(
            self._identity_modules("最后一击", "击杀方", attacker_identity, attacker_ids)
        )
        modules.append({"type": "divider"})
        modules.extend(self._identity_modules("被击杀方", "被击杀方", victim_identity, victim_ids))
        modules.extend(
            [
                {"type": "divider"},
                {
                    "type": "context",
                    "elements": [
                        self._kmarkdown(
                            f"{self._escape_kmarkdown(system_name)} · "
                            f"{len(attackers)} 人参战 · {timestamp} 北京"
                        )
                    ],
                },
                {
                    "type": "context",
                    "elements": [
                        self._kmarkdown(
                            f"[查看 zKillboard 战报]({detail_url}) · Killmail #{killmail_id}"
                        )
                    ],
                },
            ]
        )
        return {"type": "card", "theme": theme, "size": "sm", "modules": modules}

    @classmethod
    def _identity_modules(
        cls,
        title: str,
        side: str,
        identity: dict[str, str],
        ids: dict[str, int],
    ) -> list[dict[str, Any]]:
        character = cls._linked_name(identity["character"], "character", ids["character"])
        corporation = cls._linked_name(identity["corporation"], "corporation", ids["corporation"])
        alliance = cls._linked_name(identity["alliance"], "alliance", ids["alliance"])
        portrait = cls._image_url("characters", ids["character"], "portrait", size=64)
        corporation_logo = cls._image_url("corporations", ids["corporation"], "logo", size=64)
        alliance_logo = cls._image_url("alliances", ids["alliance"], "logo", size=64)
        section: dict[str, Any] = {
            "type": "section",
            "mode": "left",
            "text": cls._kmarkdown(f"**{title}**\n{character}"),
        }
        if portrait:
            section["accessory"] = cls._card_image(
                portrait, f"{side}角色头像", circle=True, size="sm"
            )
        context: list[dict[str, Any]] = []
        if corporation_logo:
            context.append(cls._card_image(corporation_logo, f"{side}军团", size="sm"))
        context.append(cls._kmarkdown(f"军团 · {corporation}"))
        corporation_row = {"type": "context", "elements": context}
        alliance_row = {"type": "context", "elements": []}
        if alliance_logo:
            alliance_row["elements"].append(
                cls._card_image(alliance_logo, f"{side}联盟", size="sm")
            )
        alliance_row["elements"].append(cls._kmarkdown(f"联盟 · {alliance}"))
        return [section, corporation_row, alliance_row]

    @classmethod
    def _linked_name(cls, name: str, entity: str, entity_id: int) -> str:
        escaped = cls._escape_kmarkdown(name)
        if entity_id <= 0:
            return escaped
        return f"[{escaped}](https://zkillboard.com/{entity}/{entity_id}/)"

    @staticmethod
    def _identity_ids(value: dict[str, Any]) -> dict[str, int]:
        return {
            "character": KbWatchFormatter._integer(value.get("character_id")),
            "corporation": KbWatchFormatter._integer(value.get("corporation_id")),
            "alliance": KbWatchFormatter._integer(value.get("alliance_id")),
        }

    @staticmethod
    def _identity(
        ids: dict[str, int], names: dict[int, str], character_fallback: str
    ) -> dict[str, str]:
        return {
            "character": names.get(ids["character"], character_fallback),
            "corporation": names.get(ids["corporation"], "无军团"),
            "alliance": names.get(ids["alliance"], "无联盟"),
        }

    @staticmethod
    def _image_url(kind: str, entity_id: int, variant: str, *, size: int = 128) -> str:
        if entity_id <= 0:
            return ""
        return (
            f"https://images.evetech.net/{kind}/{entity_id}/{variant}"
            f"?tenant=tranquility&size={size}"
        )

    @staticmethod
    def _card_image(
        url: str, alt: str, *, circle: bool = False, size: str = "lg"
    ) -> dict[str, Any]:
        return {"type": "image", "src": url, "alt": alt, "size": size, "circle": circle}

    @staticmethod
    def _kmarkdown(content: str) -> dict[str, str]:
        return {"type": "kmarkdown", "content": content}

    @staticmethod
    def _escape_kmarkdown(value: str) -> str:
        result = str(value)
        for character in ("\\", "*", "[", "]", "(", ")", "~", ">"):
            result = result.replace(character, f"\\{character}")
        return result

    @staticmethod
    def _card_style(event_type: str) -> tuple[str, str]:
        if "测试" in event_type:
            return "info", "🧪"
        if "内部" in event_type:
            return "warning", "⚠"
        if "损失" in event_type:
            return "danger", "💥"
        return "success", "⚔"

    @staticmethod
    def _integer(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _number(value: Any) -> float:
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _parse_time(cls, value: str) -> str:
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(cls._BEIJING).strftime("%m-%d %H:%M")
        except ValueError:
            return "未知"

    @staticmethod
    def _format_isk(value: float) -> str:
        for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if value >= threshold:
                return f"{value / threshold:.2f} {suffix} ISK"
        return f"{value:.2f} ISK"
