import logging

import requests

logger = logging.getLogger(__name__)


OIL_API_URL = "https://www.iamwawa.cn/oilprice/api"
# The provider returns HTTP 403 for requests' default User-Agent.
OIL_API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; astrbot-plugin-dnf/1.9)",
}
OIL_PRICE_KEYS = ("p92", "p95", "p98", "p0", "p10", "p20", "p35")


def fetch_oil_data(area: str) -> dict | None:
    try:
        response = requests.get(
            OIL_API_URL, params={"area": area}, headers=OIL_API_HEADERS, timeout=10
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.error(f"获取{area}地区油价异常: {e}")
        return None

    if not isinstance(data, dict):
        logger.warning("油价接口返回的不是对象")
        return None

    if data.get("status") == 1 and isinstance(data.get("data"), dict):
        return data["data"]

    logger.warning(f"获取{area}地区油价失败：{data.get('message', '未知错误')}")
    return None


def format_oil_info(oil_data: dict) -> str:
    lines = [
        f"📊 {oil_data.get('name', '未知地区')} 油价信息",
        f"📅 更新时间：{oil_data.get('date', '未知')}",
        f"⛽ 92号汽油：{oil_data.get('p92', '-')}元/升",
        f"⛽ 95号汽油：{oil_data.get('p95', '-')}元/升",
        f"⛽ 98号汽油：{oil_data.get('p98', '-')}元/升",
        f"⛽ 0号柴油：{oil_data.get('p0', '-')}元/升",
    ]

    for key, label in (("p10", "10号柴油"), ("p20", "20号柴油"), ("p35", "35号柴油")):
        value = oil_data.get(key)
        if value and value != "-":
            lines.append(f"⛽ {label}：{value}元/升")

    next_update = oil_data.get("next_update_time")
    if next_update:
        lines.append(f"🔄 下次更新时间：{next_update}")

    return "\n".join(lines)


def has_oil_price_changed(previous: dict | None, current: dict) -> bool:
    if previous is None:
        return True
    return any(str(previous.get(key)) != str(current.get(key)) for key in OIL_PRICE_KEYS)


def get_oil_price_by_type(oil_data: dict, oil_type: str) -> float | None:
    price = oil_data.get(f"p{oil_type}")
    if price in (None, "", "-"):
        return None
    try:
        return float(price)
    except Exception:
        return None


def calculate_oil_cost(
    oil_type: str,
    oil_price: float,
    consumption: float,
    distance: int,
    area: str = "",
) -> str:
    if distance <= 0 or consumption <= 0:
        return "❌ 油耗和里程必须大于 0"
    consumption_per_km = consumption / 100
    total_consumption = consumption_per_km * distance
    total_cost = total_consumption * oil_price
    cost_per_km = total_cost / distance

    lines = [
        "🛢️ 油价成本计算器",
        "",
    ]
    if area:
        lines.append(f"📍 地区：{area}")
    lines.extend(
        [
            "📊 计算参数：",
            f"• 油品类型：{oil_type}号",
            f"• 油价：{oil_price}元/升",
            f"• 百公里油耗：{consumption}升",
            f"• 行驶里程：{distance}公里",
            "",
            "💰 计算结果：",
            f"• 每公里油耗：{consumption_per_km:.3f}升",
            f"• 总油耗：{total_consumption:.2f}升",
            f"• 每公里成本：{cost_per_km:.2f}元",
            f"• 总成本：{total_cost:.2f}元",
            "",
        ]
    )

    if distance == 100:
        lines.append(f"💡 百公里成本：{total_cost:.2f}元")

    if consumption <= 6:
        lines.append("✅ 油耗表现优秀！")
    elif consumption <= 8:
        lines.append("👍 油耗表现良好")
    elif consumption <= 10:
        lines.append("⚠️ 油耗表现一般")
    else:
        lines.append("🔴 油耗偏高，建议检查车况")

    return "\n".join(lines)
