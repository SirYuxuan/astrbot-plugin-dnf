from __future__ import annotations

import html

from .client import ShipBonus, ShipInfo


class ShipCardRenderer:
    """生成适合聊天软件的窄版舰船资料卡。"""

    WIDTH = 620

    def render(self, ship: ShipInfo) -> str:
        role_rows = "".join(self._bonus_row(item) for item in ship.role_bonuses)
        skill_sections = "".join(
            f'<div class="skill-title">{html.escape(group.skill_name)}</div>'
            + "".join(self._bonus_row(item) for item in group.bonuses)
            for group in ship.skill_bonuses
        )
        if not role_rows:
            role_rows = '<div class="empty">暂无角色加成</div>'
        if not skill_sections:
            skill_sections = '<div class="empty">暂无技能加成</div>'

        safe_name = html.escape(ship.name)
        safe_name_en = html.escape(ship.name_en)
        safe_description = html.escape(ship.description)
        return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width={self.WIDTH},initial-scale=1">
<style>
*{{box-sizing:border-box}}html,body{{margin:0;width:{self.WIDTH}px;background:transparent}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;color:#e8edf2}}
.card{{width:{self.WIDTH}px;padding:24px 26px 22px;background:linear-gradient(145deg,#182128,#10171c);border:1px solid #34424c;border-top:3px solid #c7a862}}
.hero{{display:grid;grid-template-columns:1fr 156px;gap:18px;align-items:center}}
.kicker{{margin:0 0 5px;color:#c7a862;font-size:11px;font-weight:700;letter-spacing:.14em}}
h1{{margin:0;font-size:29px;line-height:1.12;font-weight:700}}.en{{margin-top:5px;color:#86949e;font-size:14px}}
.ship-image{{display:block;width:156px;height:156px;object-fit:contain}}
.description{{margin:15px 0 0;color:#b4bec5;font-size:13px;line-height:1.55}}
.stats{{display:grid;grid-template-columns:repeat(6,1fr);margin:20px 0;border:1px solid #34424c;background:#11191f}}
.stat{{padding:10px 4px;text-align:center;border-right:1px solid #34424c}}.stat:last-child{{border-right:0}}
.stat-value{{font-size:19px;font-weight:700}}.stat-label{{margin-top:3px;color:#82919a;font-size:10px}}
.high .stat-value{{color:#e5e9ec}}.mid .stat-value{{color:#63a8d8}}.low .stat-value{{color:#d7b95e}}.rig .stat-value{{color:#d67878}}
.section{{margin-top:17px}}.section-title{{margin:0 0 8px;padding-bottom:7px;border-bottom:1px solid #34424c;color:#d9e0e5;font-size:14px;font-weight:700}}
.skill-title{{margin:10px 0 4px;color:#c7a862;font-size:12px;font-weight:700}}
.bonus{{display:grid;grid-template-columns:56px 1fr;gap:8px;padding:4px 0;color:#bdc6cc;font-size:12px;line-height:1.3}}
.bonus-note{{display:block;padding-left:64px}}.bonus-value{{color:#69b39c;font-weight:700;text-align:right;font-variant-numeric:tabular-nums}}.empty{{color:#74828b;font-size:12px}}
.footer{{margin-top:17px;padding-top:10px;border-top:1px solid #2c3942;color:#66757e;font-size:10px;letter-spacing:.08em;text-align:right}}
</style></head><body><main class="card">
<section class="hero"><div><p class="kicker">EVE SHIP PROFILE</p><h1>{safe_name}</h1><div class="en">{safe_name_en}</div><p class="description">{safe_description}</p></div><img class="ship-image" src="{ship.image_data_url}" alt="{safe_name}"></section>
<section class="stats">
<div class="stat high"><div class="stat-value">{ship.high_slots}</div><div class="stat-label">高槽</div></div>
<div class="stat mid"><div class="stat-value">{ship.mid_slots}</div><div class="stat-label">中槽</div></div>
<div class="stat low"><div class="stat-value">{ship.low_slots}</div><div class="stat-label">低槽</div></div>
<div class="stat rig"><div class="stat-value">{ship.rig_slots}</div><div class="stat-label">改装</div></div>
<div class="stat"><div class="stat-value">{ship.turret_hardpoints}</div><div class="stat-label">炮台</div></div>
<div class="stat"><div class="stat-value">{ship.launcher_hardpoints}</div><div class="stat-label">发射器</div></div>
</section>
<section class="section"><h2 class="section-title">角色加成</h2>{role_rows}</section>
<section class="section"><h2 class="section-title">技能加成</h2>{skill_sections}</section>
<div class="footer">TYPE {ship.type_id} · TRANQUILITY</div>
</main><script id="astrbot-t2i-shiki-runtime"></script></body></html>"""

    @classmethod
    def _bonus_row(cls, bonus: ShipBonus) -> str:
        if bonus.value == 0:
            return f'<div class="bonus bonus-note">{html.escape(bonus.text)}</div>'
        return (
            '<div class="bonus">'
            f'<span class="bonus-value">{html.escape(cls._format_bonus_value(bonus))}</span>'
            f"<span>{html.escape(bonus.text)}</span>"
            "</div>"
        )

    @staticmethod
    def _format_bonus_value(bonus: ShipBonus) -> str:
        value = f"{bonus.value:+g}"
        return f"{value}%" if bonus.unit_id == 105 else value
