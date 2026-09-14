from __future__ import annotations

import base64
import html
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .client import MarketHistoryDay


@dataclass(frozen=True)
class ChartMarkup:
    html: str


class PriceChartRenderer:
    """Build a self-contained white ECharts market card for Chromium screenshots."""

    WIDTH = 1200
    HEIGHT = 760

    def render(
        self,
        type_id: int,
        item_name: str,
        history: list[MarketHistoryDay],
        *,
        quantity: int = 1,
    ) -> ChartMarkup | None:
        if not history:
            return None
        station = history[0].source == "Adam4EVE Jita 4-4"
        chinese = bool(re.search(r"[\u3400-\u9fff]", item_name))
        dates = [row.date.strftime("%m-%d") for row in history]
        middle = [round(row.average * quantity, 4) for row in history]
        buys = [round(row.lowest * quantity, 4) for row in history]
        sells = [round(row.highest * quantity, 4) for row in history]
        visible = [*middle, *buys, *sells] if station else middle
        data_min, data_max = min(visible), max(visible)
        first, latest = middle[0], middle[-1]
        change = ((latest - first) / first * 100) if first else 0.0
        change_class = "up" if change >= 0 else "down"
        quantity_text = f" × {quantity}" if quantity != 1 else ""
        icon_url = f"https://images.evetech.net/types/{type_id}/icon?size=128"

        if chinese:
            market = "吉他 4-4" if station else "区域行情"
            labels = {
                "latest": "最新中间价" if station else "最新日均价",
                "change": "30日变化",
                "range": "30日区间",
                "title": "近30日价格走势",
                "middle": "中间价" if station else "每日平均成交价",
                "sell": "最低卖价",
                "buy": "最高收价",
            }
        else:
            market = "JITA 4-4" if station else "REGIONAL"
            labels = {
                "latest": "LATEST MIDPOINT" if station else "LATEST AVERAGE",
                "change": "30D CHANGE",
                "range": "30D RANGE",
                "title": "30-DAY PRICE TREND",
                "middle": "Midpoint" if station else "Daily average",
                "sell": "Lowest sell",
                "buy": "Highest buy",
            }

        series = []
        if station:
            series.extend(
                [
                    self._series(labels["sell"], sells, "#ef6b73", "rgba(239,107,115,.05)"),
                    self._series(labels["buy"], buys, "#23ad7b", "rgba(35,173,123,.05)"),
                ]
            )
        series.append(
            self._series(
                labels["middle"],
                middle,
                "#2878ff",
                "rgba(40,120,255,.18)",
                width=4,
                show_price_labels=True,
            )
        )
        option = {
            "animation": False,
            "color": [entry["lineStyle"]["color"] for entry in series],
            "tooltip": {"show": False},
            "legend": {
                "show": True,
                "top": 2,
                "right": 18,
                "itemWidth": 22,
                "itemHeight": 3,
                "itemGap": 24,
                "icon": "roundRect",
                "textStyle": {
                    "color": "#52616d",
                    "fontFamily": "CangEr JinKai",
                    "fontSize": 13,
                },
            },
            "grid": {"left": 76, "right": 22, "top": 52, "bottom": 42},
            "xAxis": {
                "type": "category",
                "boundaryGap": False,
                "data": dates,
                "axisLine": {"lineStyle": {"color": "#d8e0e8"}},
                "axisTick": {"show": False},
                "axisLabel": {
                    "color": "#7b8792",
                    "fontFamily": "CangEr JinKai",
                    "fontSize": 12,
                    "interval": self._date_interval(len(dates)),
                    "margin": 16,
                    "showMinLabel": True,
                    "showMaxLabel": True,
                    "hideOverlap": True,
                },
                "splitLine": {"show": False},
            },
            "yAxis": {
                "type": "value",
                "scale": True,
                "min": "dataMin",
                "max": "dataMax",
                "splitNumber": 4,
                "axisLine": {"show": False},
                "axisTick": {"show": False},
                "axisLabel": {
                    "color": "#7b8792",
                    "fontFamily": "CangEr JinKai",
                    "fontSize": 12,
                    "formatter": "__ISK_FORMATTER__",
                    "margin": 16,
                },
                "splitLine": {"lineStyle": {"color": "#e7edf3", "type": "dashed"}},
            },
            "series": series,
        }
        option_json = json.dumps(option, ensure_ascii=False, separators=(",", ":")).replace(
            '"__ISK_FORMATTER__"',
            "function(value){return shortISK(value)}",
        )
        safe_name = html.escape(item_name)
        safe_market = html.escape(market)
        html_text = f"""<!doctype html>
<html lang="{"zh-CN" if chinese else "en"}"><head><meta charset="utf-8">
<meta name="viewport" content="width={self.WIDTH},initial-scale=1">
<style>
@font-face{{font-family:'CangEr JinKai';src:url('{self._font_data_url()}') format('woff2');font-weight:100 900;font-display:block}}
*{{box-sizing:border-box}}html,body{{margin:0;width:1200px;height:760px;overflow:hidden}}
body{{font-family:'CangEr JinKai',sans-serif;color:#17212b;background:#eef2f6}}
.card{{position:relative;width:1200px;height:760px;padding:40px 52px 30px;background:linear-gradient(145deg,#fff 0%,#fbfdff 68%,#f4f8fc 100%);border:1px solid #dfe6ed}}
.card:before{{content:'';position:absolute;top:-180px;right:-140px;width:520px;height:420px;border-radius:50%;background:radial-gradient(circle,rgba(40,120,255,.10),transparent 68%)}}
.header{{position:relative;display:flex;align-items:center;height:104px;gap:21px}}
.icon-box{{width:96px;height:96px;flex:none;padding:8px;border:1px solid #d8e2ec;border-radius:22px;background:linear-gradient(145deg,#fff,#edf3f8);box-shadow:0 14px 32px rgba(35,57,76,.12)}}
.icon{{display:block;width:78px;height:78px;border-radius:15px;object-fit:contain}}
.heading{{min-width:0;flex:1}}.eyebrow{{margin:0 0 7px;color:#7c8b99;font-size:13px;font-weight:600;letter-spacing:.17em}}h1{{margin:0;overflow:hidden;color:#17212b;font-size:37px;line-height:1.2;font-weight:700;text-overflow:ellipsis;white-space:nowrap}}
.badges{{display:flex;align-self:flex-start;gap:8px}}.badge{{padding:9px 14px;border:1px solid #d4e0eb;border-radius:99px;background:rgba(255,255,255,.8);color:#4f6475;font-size:13px;font-weight:600;letter-spacing:.08em;box-shadow:0 6px 18px rgba(37,61,82,.06)}}
.metrics{{position:relative;display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:20px}}
.metric{{height:89px;padding:16px 20px;border:1px solid #e0e7ee;border-radius:17px;background:rgba(255,255,255,.94);box-shadow:0 9px 28px rgba(44,65,83,.07)}}
.metric-label{{color:#85919d;font-size:13px;font-weight:600;letter-spacing:.07em}}.metric-value{{margin-top:7px;color:#1b2834;font-size:27px;line-height:1;font-weight:650;font-variant-numeric:tabular-nums}}.metric:first-child{{border-top:3px solid #2878ff}}.metric:first-child .metric-value{{color:#216de7}}.metric-value.up{{color:#199b6b}}.metric-value.down{{color:#e0525c}}
.chart-panel{{position:relative;margin-top:18px;padding:18px 17px 8px;border:1px solid #e2e9f0;border-radius:20px;background:#fff;box-shadow:0 14px 42px rgba(38,60,78,.08)}}
.chart-title{{position:absolute;z-index:2;top:20px;left:25px;color:#6f7e8b;font-size:13px;font-weight:650;letter-spacing:.1em}}#chart{{width:1058px;height:350px}}
.footer{{position:absolute;right:54px;bottom:14px;color:#a2adb7;font-size:11px;letter-spacing:.13em}}
</style></head><body><main class="card">
<header class="header"><div class="icon-box"><img class="icon" src="{icon_url}" alt=""></div><div class="heading"><p class="eyebrow">EVE MARKET INTELLIGENCE</p><h1>{safe_name}{quantity_text}</h1></div><div class="badges"><span class="badge">{safe_market}</span><span class="badge">30D</span></div></header>
<section class="metrics"><div class="metric"><div class="metric-label">{labels["latest"]}</div><div class="metric-value">{self._short_isk(latest)} ISK</div></div><div class="metric"><div class="metric-label">{labels["change"]}</div><div class="metric-value {change_class}">{change:+.2f}%</div></div><div class="metric"><div class="metric-label">{labels["range"]}</div><div class="metric-value">{self._short_isk(data_min)} – {self._short_isk(data_max)}</div></div></section>
<section class="chart-panel"><div class="chart-title">{labels["title"]}</div><div id="chart"></div></section><div class="footer">TRANQUILITY · TYPE {type_id}</div>
</main><!-- AstrBot sees this marker and skips injecting its unrelated 1.2 MB Shiki runtime. -->
<script id="astrbot-t2i-shiki-runtime"></script><script>{self._echarts_script()}</script><script>
function shortISK(value){{const n=Math.abs(value);if(n>=1e9)return(value/1e9).toFixed(2)+'B';if(n>=1e6)return(value/1e6).toFixed(2)+'M';if(n>=1e3)return(value/1e3).toFixed(2)+'K';return Number(value).toFixed(2)}}
const chart=echarts.init(document.getElementById('chart'),null,{{renderer:'svg'}});const option={option_json};chart.setOption(option);window.__EVE_CHART_READY__=true;
</script></body></html>"""
        return ChartMarkup(html_text)

    @staticmethod
    def _series(
        name: str,
        data: list[float],
        color: str,
        area_color: str,
        *,
        width: int = 2,
        show_price_labels: bool = False,
    ) -> dict:
        point_interval = max(1, len(data) // 6)
        label_indexes = set(range(0, len(data), point_interval)) | {len(data) - 1}
        chart_data: list[float | dict] = data
        if show_price_labels:
            chart_data = [
                {
                    "value": value,
                    "label": {"show": True, "formatter": PriceChartRenderer._short_isk(value)},
                }
                if index in label_indexes
                else value
                for index, value in enumerate(data)
            ]
        series = {
            "name": name,
            "type": "line",
            "data": chart_data,
            "smooth": 0.28,
            "smoothMonotone": "x",
            "showSymbol": True,
            "symbol": "circle",
            "symbolSize": 7 if show_price_labels else 5,
            "lineStyle": {"color": color, "width": width, "shadowColor": color, "shadowBlur": 5},
            "itemStyle": {"color": color},
            "label": {
                "show": False,
                "position": "top",
                "distance": 9,
                "color": color,
                "fontFamily": "CangEr JinKai",
                "fontSize": 11,
                "fontWeight": 600,
                "backgroundColor": "rgba(255,255,255,.94)",
                "borderColor": "#dce5ed",
                "borderWidth": 1,
                "borderRadius": 5,
                "padding": [3, 5],
            },
            "areaStyle": {"color": area_color, "opacity": 1} if width >= 4 else None,
            "emphasis": {"disabled": True},
            "z": 4 if width >= 4 else 3,
        }
        return series

    @staticmethod
    def _date_interval(length: int) -> int:
        return max(0, length // 7 - 1)

    @staticmethod
    @lru_cache(maxsize=1)
    def _font_data_url() -> str:
        font = Path(__file__).with_name("assets") / "CangErJinKai02-W04.woff2"
        return "data:font/woff2;base64," + base64.b64encode(font.read_bytes()).decode("ascii")

    @staticmethod
    @lru_cache(maxsize=1)
    def _echarts_script() -> str:
        return (Path(__file__).with_name("assets") / "echarts.min.js").read_text("utf-8")

    @staticmethod
    def _short_isk(value: float) -> str:
        for divisor, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
            if abs(value) >= divisor:
                return f"{value / divisor:.2f}{suffix}"
        return f"{value:.2f}"
