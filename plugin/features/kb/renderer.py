"""Render a detailed EVE killmail as a compact image card."""

from __future__ import annotations

import base64
import datetime as dt
import html
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..eve.catalog import EveCatalog
from .client import KbClient


class KbKillmailRenderer:
    """Build the image used by KB subscriptions and /kbk /kbl."""

    _BEIJING = dt.timezone(dt.timedelta(hours=8))
    _FONT_PATH = Path(__file__).parents[1] / "eve" / "assets" / "CangErJinKai02-W04.woff2"

    def __init__(self, client: KbClient, catalog: EveCatalog):
        self.client = client
        self.catalog = catalog

    def render(self, package: dict[str, Any], title: str) -> str:
        esi = package.get("esi") if isinstance(package.get("esi"), dict) else {}
        victim = esi.get("victim") if isinstance(esi.get("victim"), dict) else {}
        attackers = esi.get("attackers") if isinstance(esi.get("attackers"), list) else []
        attackers = [item for item in attackers if isinstance(item, dict)]
        attackers.sort(key=lambda item: self._integer(item.get("damage_done")), reverse=True)
        shown_attackers = attackers[:8]
        system_id = self._integer(esi.get("solar_system_id"))
        victim_ids = self._identity_ids(victim)
        attacker_ids = [self._identity_ids(item) for item in shown_attackers]
        name_ids = [*victim_ids.values(), system_id]
        for identity in attacker_ids:
            name_ids.extend(identity.values())
        names = self.client.names(name_ids)

        victim_name = self._identity_name(victim_ids, names, "未知角色")
        victim_corp = names.get(victim_ids["corporation"], "未知军团")
        victim_alliance = names.get(victim_ids["alliance"], "无联盟")
        system_name = names.get(system_id, f"星系 {system_id}" if system_id else "未知星系")
        ship_type_id = self._integer(victim.get("ship_type_id"))
        ship_name = self._type_name(ship_type_id, "未知舰船")
        total_damage = self._integer(victim.get("damage_taken")) or sum(
            self._integer(item.get("damage_done")) for item in attackers
        )
        value = self._number(
            (package.get("zkb") or {}).get("totalValue")
            if isinstance(package.get("zkb"), dict)
            else 0
        )
        event_time = self._parse_time(str(esi.get("killmail_time", "")))
        items = victim.get("items") if isinstance(victim.get("items"), list) else []
        all_item_rows = [item for item in items if isinstance(item, dict)]
        item_rows = all_item_rows[:16]

        participants = "".join(
            self._participant_row(item, names, total_damage)
            for item in shown_attackers
        )
        if not participants:
            participants = '<div class="no-data">暂无参与者详情</div>'
        if len(attackers) > len(shown_attackers):
            participants += (
                f'<div class="more">其余 {len(attackers) - len(shown_attackers)} 名参与者未展开</div>'
            )
        equipment = "".join(self._item_row(item) for item in item_rows)
        if not equipment:
            equipment = '<div class="no-data">无装备明细</div>'
        if len(all_item_rows) > len(item_rows):
            equipment += (
                f'<div class="more">另有 {len(all_item_rows) - len(item_rows)} 项物品未展开</div>'
            )

        safe_title = html.escape(title)
        safe_victim_name = html.escape(victim_name)
        safe_corp = html.escape(victim_corp)
        safe_alliance = html.escape(victim_alliance)
        safe_ship_name = html.escape(ship_name)
        safe_system = html.escape(system_name)
        portrait_url = self._image_url("characters", victim_ids["character"], "portrait", 128)
        ship_url = self._image_url("types", ship_type_id, "render", 128)
        corp_url = self._image_url("corporations", victim_ids["corporation"], "logo", 64)
        alliance_url = self._image_url("alliances", victim_ids["alliance"], "logo", 64)
        item_count = len(all_item_rows)
        participant_count = len(attackers)
        font_url = self._font_data_url()
        return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=760,initial-scale=1">
<style>
@font-face{{font-family:CangErJinKai;src:url('{font_url}') format('woff2');font-display:block}}
:root{{--bg:#17191f;--head:#24222b;--bar:#34313d;--line:#4c4755;--text:#f3f0f4;--muted:#aaa5b1;--blue:#68a9ee;--green:#8fd7b5;--red:#ee8b86;--gold:#eac37d}}
*{{box-sizing:border-box}}html,body{{margin:0;width:760px;background:transparent}}
body{{font-family:CangErJinKai,'PingFang SC','Microsoft YaHei',sans-serif;color:var(--text)}}
.report{{width:760px;overflow:hidden;background:var(--bg);border:1px solid #5c5663;border-radius:12px;box-shadow:0 16px 45px #0009}}
.hero{{height:160px;padding:14px 15px;display:flex;align-items:flex-start;gap:11px;background:linear-gradient(112deg,#2c2934,#222329 64%,#2b2730);border-bottom:1px solid var(--line);position:relative}}
.hero:after{{content:'';position:absolute;left:0;right:0;bottom:0;height:2px;background:linear-gradient(90deg,#6dbca2,#6a5873 48%,#d3a567);opacity:.78}}
.portrait,.ship img{{width:96px;height:96px;object-fit:cover;flex:none;border:1px solid #6a6270;border-radius:8px;box-shadow:0 4px 12px #0007;background:#15151b}}
.ship{{width:96px;flex:none;text-align:center;color:#c3bad0;font-size:13px;line-height:18px}}.ship img{{display:block;margin-bottom:4px}}
.summary{{padding-top:1px;min-width:0;flex:1}}.summary h1{{font-size:22px;line-height:27px;margin:0 0 3px;color:#f4f1f5;white-space:nowrap;font-weight:700;letter-spacing:.3px}}
.org{{height:24px;margin-bottom:6px;display:flex;align-items:center;gap:6px;font-size:15px;color:#f0edf2;white-space:nowrap;overflow:hidden}}.org img{{width:22px;height:22px;object-fit:cover;flex:none;border:1px solid #756b78;border-radius:4px}}.org .alliance-logo{{width:24px;height:24px;margin-left:5px}}
.event{{height:22px;font-size:14px;line-height:22px;color:#c5bfcd;white-space:nowrap}}.time{{height:22px;font-size:13px;line-height:22px;color:#b5afbc;white-space:nowrap}}.location{{color:var(--blue);font-weight:700}}
.loss{{margin-top:2px;font-size:14px;line-height:22px;color:var(--muted);white-space:nowrap}}.loss b{{font-size:16px;color:var(--red);font-weight:700}}
.columns{{display:grid;grid-template-columns:360px minmax(0,1fr);align-items:stretch;background:#15171d}}
.panel{{min-width:0;overflow:hidden}}.participants{{border-right:1px solid var(--line)}}
.col-head{{min-height:34px;padding:0 12px;display:flex;align-items:center;justify-content:space-between;background:linear-gradient(90deg,#3b3745,#312f39);border-bottom:1px solid #58515f;font-size:14px;font-weight:700;color:#f2eff4;letter-spacing:.2px}}.count{{margin-left:4px;font-size:12px;color:#bbb2c2;font-weight:400}}
.damage-total{{font-size:12px;color:#e9a59b;font-weight:400;white-space:nowrap}}.damage-total b{{margin-left:3px;color:#f4b4a6;font-size:14px}}
.last-hit{{height:20px;padding:1px 12px;color:#d8d2db;font-size:12px;line-height:18px;background:#1a1b21;border-bottom:1px solid #3b3944}}.last-hit:before{{content:'';display:inline-block;width:5px;height:5px;margin:0 6px 2px 0;border-radius:50%;background:#e58b84}}
.people,.equipment{{background:#15171d}}.person{{display:flex;gap:6px;min-height:76px;padding:6px 9px;border-bottom:1px solid #393741;background:linear-gradient(100deg,#23232c,#191a20 78%)}}
.avatar{{width:56px;height:56px;object-fit:cover;flex:none;border:1px solid #665e6d;border-radius:6px;background:#25232b;box-shadow:0 2px 8px #0007}}.avatar-fallback{{display:flex;align-items:center;justify-content:center;color:#a9a2b0;font-size:10px}}
.icons{{width:28px;height:56px;display:flex;flex-direction:column;gap:4px;flex:none}}.icons img{{width:28px;height:26px;object-fit:cover;border:1px solid #625969;border-radius:4px;background:#25232c}}
.person-main{{min-width:0;flex:1}}.name{{height:19px;line-height:19px;font-size:14px;font-weight:700;color:#f2eff4;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.final{{display:inline-block;margin-left:4px;padding:0 5px;border:1px solid #a35d5c;border-radius:8px;background:#713a4140;color:#f4aaa3;font-size:11px;line-height:15px;vertical-align:1px;font-weight:400}}
.shipline{{height:18px;line-height:18px;font-size:12px;color:#ddd6e1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.meta{{height:13px;line-height:13px;font-size:11px;color:#aaa4b1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.damage{{height:17px;line-height:17px;font-size:12px;color:#b0aeba;white-space:nowrap}}.damage b{{color:var(--gold);font-size:13px}}.damage .pct{{color:#c5bfca;margin-left:4px}}
.item{{height:33px;display:flex;align-items:center;gap:7px;padding:3px 13px;border-bottom:1px solid #35343d;color:#ddd8e0;font-size:12px}}.item img{{width:26px;height:26px;object-fit:cover;border:1px solid #5b5363;border-radius:4px;background:#25232c;flex:none}}.item-name{{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.item-qty{{color:#c1bac7;font-size:11px;white-space:nowrap}}.drop{{color:var(--green)}}.destroy{{color:var(--red)}}
.no-data{{padding:10px 15px;color:#afa8b4;font-size:13px}}.more{{padding:6px 12px;color:#aaa3af;font-size:11px;text-align:center;border-bottom:1px solid #393741}}
.total{{height:25px;padding:0 14px;display:grid;grid-template-columns:1fr 1fr auto;gap:12px;align-items:center;background:linear-gradient(90deg,#293a37,#37303d);border-top:1px solid #5a5360;color:#d0c9d2;font-size:12px;line-height:20px}}.total b{{color:var(--green)}}.total .value{{color:var(--gold);font-weight:700}}.byline{{justify-self:end;color:#d6c8da;font-size:11px;letter-spacing:.3px}}
</style></head><body><main class="report">
<header class="hero"><img class="portrait" src="{portrait_url}" alt="被击杀角色"><div class="ship"><img src="{ship_url}" alt="{safe_ship_name}">{safe_ship_name}</div><div class="summary"><h1>{safe_victim_name}</h1><div class="org">{self._logo(corp_url, '军团')}<span>{safe_corp}</span>{self._logo(alliance_url, '联盟', True)}<span>{safe_alliance}</span></div><div class="event">{safe_title}</div><div class="time">{event_time} · 地点：<strong class="location">{safe_system}</strong></div><div class="loss">损失装备 <b>{self._format_isk(value)}</b></div></div></header>
<main class="columns"><section class="panel participants"><div class="col-head"><span>参与者<span class="count">({participant_count})</span></span><span class="damage-total">共受到伤害：<b>{total_damage:,}</b></span></div><div class="last-hit">最后一击</div><div class="people">{participants}</div></section><section class="panel equipment"><div class="col-head"><span>装备与明细<span class="count">({item_count})</span></span><span class="action">掉落 / 损毁</span></div>{equipment}</section></main>
<footer class="total"><span>总掉落: <b>{self._format_isk(self._number((package.get('zkb') or {{}}).get('droppedValue')) if isinstance(package.get('zkb'), dict) else 0)}</b></span><span>总价值: <span class="value">{self._format_isk(value)}</span></span><span class="byline">By: 烟雨机器人</span></footer></main></body></html>"""

    def _participant_row(
        self,
        attacker: dict[str, Any],
        names: dict[int, str],
        total_damage: int,
    ) -> str:
        identity = self._identity_ids(attacker)
        name = self._identity_name(identity, names, "NPC / 未知角色")
        corp = names.get(identity["corporation"], "无军团")
        alliance = names.get(identity["alliance"], "无联盟")
        ship_id = self._integer(attacker.get("ship_type_id"))
        weapon_id = self._integer(attacker.get("weapon_type_id"))
        ship = self._type_name(ship_id, "未知舰船")
        weapon = self._type_name(weapon_id, "未知武器") if weapon_id else "未知武器"
        damage = self._integer(attacker.get("damage_done"))
        percentage = damage / total_damage * 100 if total_damage else 0
        final = '<span class="final">最后一击</span>' if attacker.get("final_blow") else ""
        avatar = self._image_url("characters", identity["character"], "portrait", 64)
        avatar_markup = (
            f'<img class="avatar" src="{avatar}" alt="{html.escape(name)}">'
            if avatar
            else '<div class="avatar avatar-fallback">NPC</div>'
        )
        ship_url = self._image_url("types", ship_id, "icon", 64)
        weapon_url = self._image_url("types", weapon_id, "icon", 64)
        icons = "".join(
            f'<img src="{url}" alt="{html.escape(label)}">'
            for url, label in ((ship_url, ship), (weapon_url, weapon))
            if url
        )
        if not icons:
            icons = '<div class="avatar avatar-fallback" style="width:28px;height:26px">?</div>'
        return (
            f'<article class="person">{avatar_markup}<div class="icons">{icons}</div>'
            f'<div class="person-main"><div class="name">{html.escape(name)}{final}</div>'
            f'<div class="shipline">{html.escape(ship)} / {html.escape(weapon)}</div>'
            f'<div class="meta">{html.escape(corp)} · {html.escape(alliance)}</div>'
            f'<div class="damage"><b>{damage:,}</b><span class="pct">({percentage:.1f}%)</span></div>'
            "</div></article>"
        )

    def _item_row(self, item: dict[str, Any]) -> str:
        type_id = self._integer(item.get("item_type_id"))
        name = self._type_name(type_id, f"Type {type_id}")
        dropped = self._integer(item.get("quantity_dropped"))
        destroyed = self._integer(item.get("quantity_destroyed"))
        quantity = dropped or destroyed or 1
        if dropped:
            state = f'<span class="item-qty drop">掉落 ×{quantity:,}</span>'
        else:
            state = f'<span class="item-qty destroy">损毁 ×{quantity:,}</span>'
        icon = self._image_url("types", type_id, "icon", 64)
        icon_markup = f'<img src="{icon}" alt="{html.escape(name)}">' if icon else ""
        return f'<div class="item">{icon_markup}<span class="item-name">{html.escape(name)}</span>{state}</div>'

    def _type_name(self, type_id: int, fallback: str) -> str:
        item = self.catalog.get_type(type_id) if type_id > 0 else None
        return ((item.name_zh or item.name_en) if item else fallback).strip()

    @staticmethod
    def _identity_ids(value: dict[str, Any]) -> dict[str, int]:
        return {
            "character": KbKillmailRenderer._integer(value.get("character_id")),
            "corporation": KbKillmailRenderer._integer(value.get("corporation_id")),
            "alliance": KbKillmailRenderer._integer(value.get("alliance_id")),
        }

    @staticmethod
    def _identity_name(identity: dict[str, int], names: dict[int, str], fallback: str) -> str:
        return names.get(identity["character"], fallback)

    @staticmethod
    def _image_url(kind: str, entity_id: int, variant: str, size: int) -> str:
        if entity_id <= 0:
            return ""
        return f"https://images.evetech.net/{kind}/{entity_id}/{variant}?tenant=tranquility&size={size}"

    @staticmethod
    def _logo(url: str, alt: str, alliance: bool = False) -> str:
        class_name = ' class="alliance-logo"' if alliance else ""
        return f'<img{class_name} src="{url}" alt="{alt}">' if url else ""

    @classmethod
    def _parse_time(cls, value: str) -> str:
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(cls._BEIJING).strftime("%Y-%m-%d %H:%M:%S UTC+8")
        except ValueError:
            return "未知时间 UTC+8"

    @staticmethod
    def _format_isk(value: float) -> str:
        for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if value >= threshold:
                return f"{value / threshold:.2f} {suffix} ISK"
        return f"{value:.0f} ISK"

    @staticmethod
    def _number(value: Any) -> float:
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _integer(value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @classmethod
    @lru_cache(maxsize=1)
    def _font_data_url(cls) -> str:
        try:
            return "data:font/woff2;base64," + base64.b64encode(cls._FONT_PATH.read_bytes()).decode("ascii")
        except OSError:
            return ""
