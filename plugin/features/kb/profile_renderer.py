"""Render the public character profile as a self-contained image card."""

import collections
import datetime as dt
import html
from pathlib import Path

from .assessment import build_assessment
from .renderer import KbKillmailRenderer


class KbProfileRenderer:
    def __init__(self, catalog):
        self.catalog = catalog

    def render(self, data, *, now=None):
        s = data["stats"]
        ch = data["character"]
        hist = sorted(data["history"], key=lambda r: r["start_date"], reverse=True)
        cid, name = data["identity"]
        records = data["records"]
        names = data["names"]
        typenames = dict(data.get("type_names", {}))
        for tid in {r["victim"]["ship_type_id"] for r in records} | {
            a.get("ship_type_id", 0)
            for r in records
            for a in r["attackers"]
            if a.get("character_id") == cid
        }:
            item = self.catalog.get_type(tid) if tid else None
            if item:
                typenames[tid] = item.name_zh or item.name_en
        shipkills = collections.Counter()
        shiploss = collections.Counter()
        systems = collections.Counter()
        hours = [0] * 24
        heat = [[0] * 4 for _ in range(7)]
        tz = dt.timezone(dt.timedelta(hours=8))
        now = now or dt.datetime.now(tz)
        for r in records:
            lost = r["victim"].get("character_id") == cid
            if lost:
                shiploss[r["victim"]["ship_type_id"]] += 1
            else:
                own = next((a for a in r["attackers"] if a.get("character_id") == cid), None)
                if own and own.get("ship_type_id"):
                    shipkills[own["ship_type_id"]] += 1
            systems[r["solar_system_id"]] += 1
            t = dt.datetime.fromisoformat(r["killmail_time"].replace("Z", "+00:00")).astimezone(tz)
            hours[t.hour] += 1
            heat[t.weekday()][t.hour // 6] += 1

        def esc(value):
            return html.escape(str(value))

        def image(kind, entity_id, variant="icon", size=64):
            return KbKillmailRenderer._image_url(kind, entity_id, variant, size)

        def isk(v):
            v = float(v or 0)
            if v >= 1e8:
                return f"{v / 1e8:,.2f} 亿"
            if v >= 1e4:
                return f"{v / 1e4:,.1f} 万"
            return f"{v:,.0f}"

        out = []
        out.append(
            f'<main class="report"><header class="hero"><img class="portrait" src="{image("characters", cid, "portrait", 256)}"><div class="identity"><h1>{esc(name)}</h1><div class="subtitle">ID: {cid} · zKillboard 角色战力报告</div><div class="org"><img src="{image("corporations", ch["corporation_id"], "logo")}">{esc(names.get(ch["corporation_id"], "未知军团"))}</div><div class="org"><img src="{image("alliances", ch.get("alliance_id", 0), "logo")}">{esc(names.get(ch.get("alliance_id", 0), "无联盟"))}</div><div class="profile-meta">安全等级 <b>{ch.get("security_status", 0):.2f}</b> · 生日 <b>{ch.get("birthday", "未知")[:10]}</b><br>最近 KM 抽样 <b>{len(records)} 条</b>（击杀+战损）</div></div></header>'
        )
        kills = s.get("shipsDestroyed", 0)
        loss = s.get("shipsLost", 0)
        solo = s.get("soloKills", 0)
        danger = s.get("dangerRatio", 0)
        eff = s.get("iskDestroyed", 0) / (s.get("iskDestroyed", 0) + s.get("iskLost", 0) or 1) * 100
        out.append(
            f'<div class="metrics"><div class="metric"><strong>{kills} <em>/ {loss}</em></strong><small>累计击杀 / 战损</small></div><div class="metric"><strong class="green">{isk(s.get("iskDestroyed"))}</strong><small>ISK 摧毁</small></div><div class="metric"><strong class="red">{isk(s.get("iskLost"))}</strong><small>ISK 损失</small></div><div class="metric"><strong class="gold">{solo} / {kills - solo}</strong><small>Solo / Team 击杀</small></div></div>'
        )
        out.append('<div class="ratings">')
        for label, v, w, color in [
            ("危险指数 Dangerous", f"{danger:.0f}%", danger, "var(--green)"),
            ("ISK 效率", f"{eff:.0f}%", eff, "var(--cyan)"),
            ("平均同伙规模", str(s.get("avgGangSize", "—")), 100, "var(--gold)"),
        ]:
            out.append(
                f'<div class="rating">{label}<strong style="color:{color}">{v}</strong><div class="track"><i style="width:{min(100, max(0, w))}%;background:{color}"></i></div></div>'
            )
        out.append("</div>")
        assessment = data.get("assessment") or build_assessment(data, now=now)
        out.append(self._assessment_html(assessment))
        out.append(
            '<div class="section-title">角色军团历史 <small>按加入时间倒序 · 日期 UTC+8</small></div><div class="history">'
        )
        for i, r in enumerate(hist[:8]):
            start = dt.datetime.fromisoformat(r["start_date"].replace("Z", "+00:00")).astimezone(tz)
            end = (
                now
                if i == 0
                else dt.datetime.fromisoformat(
                    hist[i - 1]["start_date"].replace("Z", "+00:00")
                ).astimezone(tz)
            )
            days = (end - start).days
            out.append(
                f'<div class="history-row"><span class="rank">{i + 1}</span><img src="{image("corporations", r["corporation_id"], "logo")}"><span class="corp-name {"current" if i == 0 else ""}">{esc(names.get(r["corporation_id"], r["corporation_id"]))}</span><span class="date">{start:%Y-%m-%d}<br>任职 {days} 天{" · 至今" if i == 0 else ""}</span></div>'
            )
        out.append(
            f'</div><div class="more">共 {len(hist)} 条公开军团记录 · 最多展示 8 条</div><div class="section-title">近期常用舰船 / 损失舰船 / 活跃星系 <small>以最近 {len(records)} 条 KM 统计</small></div><div class="ship-stats">'
        )
        for title, cls, counts, kind in [
            ("常用舰船（击杀）", "green", shipkills, "ship"),
            ("损失舰船", "red", shiploss, "ship"),
            ("活跃星系", "", systems, "system"),
        ]:
            out.append(f'<section class="stat-col"><div class="stat-heading {cls}">{title}</div>')
            if not counts:
                out.append('<div class="empty">暂无公开记录</div>')
            for key, n in counts.most_common(8):
                icon = f'<img src="{image("types", key)}">' if kind == "ship" else ""
                label = typenames.get(key, str(key)) if kind == "ship" else names.get(key, str(key))
                out.append(
                    f'<div class="stat-row {"system" if kind == "system" else ""}">{icon}<span>{esc(label)}</span><small>×{n}</small></div>'
                )
            out.append("</section>")
        out.append(
            '</div><div class="section-title">近 12 个月战斗趋势 <small>击杀数（绿）/ 阵亡数（红）</small></div><div class="trend"><svg viewBox="0 0 700 160"><path class="gridline" d="M13 10H655 M13 37H655 M13 64H655 M13 91H655 M13 118H655"/>'
        )
        monthkeys = []
        for back in range(11, -1, -1):
            m = now.year * 12 + now.month - 1 - back
            y, mon = divmod(m, 12)
            monthkeys.append(f"{y}{mon + 1:02}")
        months = s.get("months", {})
        maxv = max(
            4,
            max(
                [
                    months.get(m, {}).get(k, 0)
                    for m in monthkeys
                    for k in ["shipsDestroyed", "shipsLost"]
                ]
                + [0]
            ),
        )
        maxv = ((maxv + 3) // 4) * 4
        for key, color in [("shipsDestroyed", "#8dd2b7"), ("shipsLost", "#ed8984")]:
            points = " ".join(
                f"{13 + i * 58},{127 - months.get(m, {}).get(key, 0) / maxv * 108:.2f}"
                for i, m in enumerate(monthkeys)
            )
            out.append(
                f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>'
            )
        for i, m in enumerate(monthkeys):
            out.append(f'<text x="{13 + i * 58}" y="147">{m[-2:]}</text>')
        for i in range(5):
            out.append(f'<text x="668" y="{14 + i * 27}">{maxv * (4 - i) / 4:g}</text>')
        out.append(
            f'</svg></div><div class="section-title">活跃时段分布 <small>最近 {len(records)} 条 KM · 本地时区（UTC+8）</small></div><div class="activity-chart"><svg viewBox="0 0 700 114">'
        )
        for i, v in enumerate(hours):
            h = v / (max(hours) or 1) * 67
            out.append(f'<rect x="{36 + i * 25.5}" y="{92 - h}" width="19" height="{h}" rx="2"/>')
            if i % 2 == 0:
                out.append(f'<text x="{45 + i * 25.5}" y="109">{i:02}</text>')
        out.append(
            '</svg></div><div class="heat-wrap"><div class="heatmap"><div class="heat-label"></div>'
        )
        for t in ["00–05", "06–11", "12–17", "18–23"]:
            out.append(f'<div class="heat-label">{t}</div>')
        maxheat = max(max(r) for r in heat) or 1
        for i, row in enumerate(heat):
            out.append(f'<div class="heat-label day">周{"一二三四五六日"[i]}</div>')
            for v in row:
                out.append(
                    f'<div class="cell" style="background:rgba(182,165,212,{0.12 + 0.88 * v / maxheat:.3f})">{v or ""}</div>'
                )
        out.append(
            '</div></div><div class="section-title">最近公开 KM <small>最多显示 10 条 · 时间 UTC+8</small></div><div class="killmails">'
        )
        for r in records[:10]:
            t = dt.datetime.fromisoformat(r["killmail_time"].replace("Z", "+00:00")).astimezone(tz)
            lost = r["victim"].get("character_id") == cid
            tid = r["victim"]["ship_type_id"]
            label = "损失" if lost else "击杀"
            color = ' style="color:var(--red);border-color:#78383d"' if lost else ""
            out.append(
                f'<div class="km-row"><img src="{image("types", tid)}"><span class="km-date">{t:%m-%d %H:%M}</span><span class="badge"{color}>{label}</span><span class="km-ship">{esc(typenames.get(tid, tid))}</span><strong>{isk(r.get("zkb", {}).get("totalValue", 0))}</strong></div>'
            )
        if not records:
            out.append(
                '<div class="empty" style="height:35px;padding-left:13px">暂无公开 KM 记录</div>'
            )
        out.append(
            f'</div><footer class="footer"><span>数据来源 zkillboard.com / ESI · {now:%m-%d %H:%M} UTC+8</span><span>By: 烟雨机器人</span></footer></main></body></html>'
        )

        if data.get("warnings"):
            out.insert(
                1,
                '<div class="profile-note" style="height:28px;padding:6px 13px;color:var(--gold)">部分数据暂不可用：'
                + esc("；".join(data["warnings"]))
                + "</div>",
            )
        height = (
            2
            + 757
            + 176
            + 61
            + 60
            + 5 * 27
            + 9
            + 43 * min(8, len(hist))
            + 39
            + 234
            + 182
            + 123
            + 286
            + 35 * max(1, min(10, len(records)))
            + 29
            + (28 if data.get("warnings") else 0)
        )
        css = Path(__file__).with_name("profile.css").read_text()
        font = KbKillmailRenderer._font_data_url()
        head = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=748,initial-scale=1"><meta name="astrbot-render-size" content="748x{height}"><title>KBINFO 角色战力报告</title><style>@font-face{{font-family:CangEr;src:url('{font}') format('woff2');font-display:block}}{css}</style></head>"""
        return head + "<body>" + "".join(out)

    @staticmethod
    def _assessment_html(a):
        def esc(value):
            return html.escape(str(value))

        def score(v):
            return f"{v:.1f} / 10" if v is not None else "样本不足"

        parts = [
            '<div class="section-title">战力评估 <small>舰队表现与单兵能力分开看</small></div><section class="assessment">',
            f'<div class="assessment-label">{esc(a["label"])}</div>',
            f'<div class="assessment-source">{esc(a["source"])} · 数据：zKillboard</div>',
            '<div class="assessment-scores">',
        ]
        for (label, value), color in zip(a["scores"].items(), ["gold", "green", "cyan", "red"]):
            parts.append(
                f'<div>{esc(label)}<b>{score(value)}</b><div class="track"><i style="width:{(value or 0) * 10}%;background:var(--{color})"></i></div></div>'
            )
        parts.append(f"</div><blockquote>{esc(a['summary'])}</blockquote>")
        for title, key, color in [
            ("强的地方", "strengths", "green"),
            ("弱的地方", "weaknesses", "red"),
        ]:
            parts.append(
                f'<div class="assessment-list"><strong style="color:var(--{color})">{title}</strong><ul>'
            )
            parts.extend(f"<li>{esc(line)}</li>" for line in a[key])
            parts.append("</ul></div>")
        parts.append(
            f'<div class="assessment-total">总体评分：舰队作战 {score(a["fleet"])} · 单人作战 {score(a["solo"])}</div>'
        )
        parts.append('<div class="assessment-conclusion">')
        for title, key in [
            ("结论", "conclusion"),
            ("招人视角", "recruiter"),
            ("对手视角", "opponent"),
        ]:
            parts.append(f"<p><b>{title}</b> {esc(a[key])}</p>")
        parts.append(
            '</div><div class="assessment-source">评分为公开战绩代理指标；出勤表示公开战斗频次，不代表在线时长。近期分析最多抽样 400 条 KM。</div></section>'
        )
        return "".join(parts)
