import datetime
import logging
import re
import time

import requests

logger = logging.getLogger(__name__)


EGG_API_URL = "http://www.quotn.cn/e/search"


def parse_egg_args(message: str) -> tuple[str, str | None]:
    args = message.split("蛋价", 1)[1].strip() if "蛋价" in message else message.strip()
    if not args:
        return "", None

    parts = args.split()
    if parts and parts[-1].isdigit() and len(parts[-1]) == 8:
        date_str = parts[-1]
        area = " ".join(parts[:-1]).strip()
    else:
        date_str = None
        area = " ".join(parts).strip()

    if area:
        match = re.search(r"[\u4e00-\u9fff]+", area)
        area = match.group(0) if match else area
    return area, date_str


def fetch_egg_prices(area_name: str, date_str: str) -> list[dict]:
    params = {
        "k": area_name or "",
        "areaName": area_name or "",
        "pDate": date_str,
        "_": str(int(time.time() * 1000)),
    }
    try:
        resp = requests.get(EGG_API_URL, params=params, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"蛋价查询请求失败: {e}")
        return []

    try:
        data = resp.json()
    except Exception:
        data = None

    results = _parse_egg_json(data)
    if results:
        return results

    pattern = re.compile(
        r"([\u4e00-\u9fff\w\-\s\/（）()]{2,60}?)\s*[：:\-\s]{0,3}\s*([0-9]+(?:\.[0-9]+)?)\s*(?:元|元/斤|元/公斤)"
    )
    for title, price_s in pattern.findall(resp.text):
        try:
            price = float(price_s)
        except Exception:
            price = None
        results.append({"title": title.strip(), "price": price})
    return results


def format_egg_prices(area: str, date_str: str | None = None, limit: int = 10) -> str:
    today_str = date_str or datetime.date.today().strftime("%Y%m%d")
    try:
        query_date = datetime.datetime.strptime(today_str, "%Y%m%d").date()
    except Exception:
        query_date = datetime.date.today()
        today_str = query_date.strftime("%Y%m%d")

    yesterday_str = (query_date - datetime.timedelta(days=1)).strftime("%Y%m%d")
    today_items = fetch_egg_prices(area, today_str)
    yesterday_items = fetch_egg_prices(area, yesterday_str)
    return format_egg_items(today_items, yesterday_items, query_date, limit)


def format_egg_items(
    today_items: list[dict], yesterday_items: list[dict], query_date: datetime.date, limit: int = 10
) -> str:
    lines = [f"返回查询结果（{query_date.strftime('%Y-%m-%d')}前{limit}条）："]
    if not today_items:
        lines.append("未查询到蛋价数据")
        return "\n".join(lines)

    lines.append("")
    lines.append(f"查询结果（今日前{limit}条）：")
    yesterday_price_map = _build_yesterday_price_map(yesterday_items)
    seen = set()
    count = 0

    for item in today_items:
        title = _format_area_title(item)
        price = item.get("price")
        up_time = item.get("upTime")
        y_price = item.get("yPrice")
        if y_price is None:
            y_price = yesterday_price_map.get((item.get("cName") or "", item.get("aName") or ""))

        key = (title, float(price) if isinstance(price, (int, float)) else price, up_time)
        if key in seen:
            continue
        seen.add(key)

        count += 1
        if count > limit:
            break

        price_text = (
            f"{price:.2f}元"
            if isinstance(price, (int, float))
            else (str(price) if price is not None else "-")
        )
        change = _format_price_change(price, y_price)
        if up_time:
            lines.append(f"{count} .{title} {up_time} {price_text}({change})")
        else:
            lines.append(f"{count} .{title} {price_text}({change})")

    return "\n".join(lines)


def _parse_egg_json(data: object) -> list[dict]:
    results = []
    if isinstance(data, dict):
        data_list = None
        body = data.get("body") if isinstance(data.get("body"), dict) else None
        if body and isinstance(body.get("dataList"), list):
            data_list = body["dataList"]
        elif isinstance(data.get("dataList"), list):
            data_list = data["dataList"]

        if data_list:
            return [_parse_data_list_item(item) for item in data_list if isinstance(item, dict)]

    _collect_price_items(data, results)
    return results


def _parse_data_list_item(item: dict) -> dict:
    c_name = item.get("cName") or ""
    a_name = item.get("aName") or ""
    title = (
        f"{c_name}{a_name}" if (c_name or a_name) else (item.get("aName") or item.get("name") or "")
    )
    return {
        "title": title.strip(),
        "price": _extract_float(
            item.get("tPrice")
            or item.get("price")
            or item.get("priceText")
            or item.get("金额")
            or item.get("yPrice")
        ),
        "upTime": item.get("upTime") or None,
        "cName": c_name,
        "aName": a_name,
        "yPrice": _extract_float(item.get("yPrice")),
    }


def _collect_price_items(obj: object, results: list[dict]) -> None:
    if isinstance(obj, dict):
        for key in ("price", "priceText", "金额"):
            if key in obj:
                results.append(
                    {
                        "title": (
                            obj.get("title") or obj.get("name") or obj.get("标题") or ""
                        ).strip(),
                        "price": _extract_float(obj.get(key)),
                        "utime": _format_time(obj),
                    }
                )
                return
        for value in obj.values():
            _collect_price_items(value, results)
    elif isinstance(obj, list):
        for item in obj:
            _collect_price_items(item, results)


def _extract_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value))
    except Exception:
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(value))
        return float(match.group(1)) if match else None


def _format_time(obj: dict) -> str | None:
    for key in ("uTime", "utime", "u_time", "time", "date", "pubTime", "pubtime", "报价时间"):
        raw = obj.get(key)
        if not raw:
            continue
        try:
            if isinstance(raw, (int, float)) or (isinstance(raw, str) and raw.isdigit()):
                timestamp = int(raw)
                if timestamp > 10**12:
                    timestamp //= 1000
                return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
            return str(raw)[:19]
        except Exception:
            return str(raw)
    return None


def _build_yesterday_price_map(items: list[dict]) -> dict[tuple[str, str], float]:
    price_map = {}
    for item in items:
        key = (item.get("cName") or "", item.get("aName") or "")
        price = item.get("price") if item.get("price") is not None else item.get("yPrice")
        if price is not None:
            price_map[key] = price
    return price_map


def _format_area_title(item: dict) -> str:
    c_name = item.get("cName") or ""
    a_name = item.get("aName") or ""
    if c_name and a_name:
        return f"{c_name}-{a_name}" if c_name != a_name else c_name
    if c_name or a_name:
        return c_name or a_name
    return item.get("title") or "-"


def _format_price_change(price: object, y_price: object) -> str:
    try:
        if isinstance(price, (int, float)) and isinstance(y_price, (int, float)) and y_price != 0:
            diff_pct = (price - y_price) / y_price * 100
            pct = round(abs(diff_pct))
            if diff_pct > 0:
                return f"涨{pct}%"
            if diff_pct < 0:
                return f"跌{pct}%"
    except Exception:
        pass
    return "平"
