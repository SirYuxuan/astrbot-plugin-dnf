"""框架事件适配与一致的异常回复，不包含查询、解析或监控逻辑。"""

import asyncio
import hashlib
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from astrbot.api import logger

_CHART_RENDER_CACHE_SECONDS = 600
_chart_render_cache: dict[str, tuple[float, str]] = {}
_chart_render_flights: dict[str, asyncio.Task[str]] = {}


def message_text(event) -> str:
    message = getattr(event, "message_str", None)
    if message is not None:
        return str(message).strip()
    getter = getattr(event, "get_message_str", None)
    return str(getter() if callable(getter) else event).strip()


def is_admin_event(event) -> bool:
    role = getattr(event, "role", "")
    return str(getattr(role, "value", role)).casefold() == "admin"


def actor_id(event) -> str:
    sender = getattr(event, "sender", None)
    sender_id = getattr(sender, "user_id", "")
    getter = getattr(event, "get_sender_id", None)
    return str(sender_id or (getter() if callable(getter) else ""))


def is_group_event(event) -> bool:
    getter = getattr(event, "get_group_id", None)
    if callable(getter):
        return bool(getter())
    message_obj = getattr(event, "message_obj", None)
    return bool(getattr(message_obj, "group_id", None))


def platform_name(event) -> str:
    getter = getattr(event, "get_platform_name", None)
    if callable(getter):
        return str(getter()).strip()
    return str(getattr(event, "platform_name", "")).strip()


def unified_origin(event) -> str:
    return str(getattr(event, "unified_msg_origin", "")).strip()


def prevent_default_reply(event) -> None:
    """Keep a matched plugin command from falling through to AstrBot's default LLM."""
    setter = getattr(event, "should_call_llm", None)
    if callable(setter):
        # Despite the historical method name, True marks this event as handled and
        # makes ProcessStage skip its implicit/default agent request.
        setter(True)
    else:
        # Compatibility with lightweight adapters and older AstrBot event objects.
        event.call_llm = True


def stop_event_propagation(event) -> None:
    """阻止同一消息继续命中 AstrBot 内置或其他插件处理器。"""
    stopper = getattr(event, "stop_event", None)
    if callable(stopper):
        stopper()


async def query_result(
    event,
    label: str,
    query: Callable[..., Awaitable[str]],
    *args,
    error_text: str | None = None,
    **kwargs,
):
    try:
        text = await query(*args, **kwargs)
    except Exception:
        logger.exception("%s查询异常", label)
        text = error_text or f"{label}查询出现异常，请稍后重试"
    return event.plain_result(text)


async def eve_query_results(
    event,
    query: Callable[..., Awaitable],
    *args,
    html_renderer: Callable[..., Awaitable[str]] | None = None,
    **kwargs,
) -> list:
    """Adapt an EVE reply to one AstrBot message, including the chart when present."""
    try:
        reply = await query(*args, **kwargs)
    except Exception:
        logger.exception("EVE 市场查询异常")
        return [event.plain_result("EVE 市场查询出现异常，请稍后重试")]
    if not reply.chart_html or html_renderer is None:
        return [event.plain_result(reply.text)]
    import astrbot.api.message_components as Comp

    cache_key = hashlib.sha256(reply.chart_html.encode()).hexdigest()
    try:
        rendered = await _render_chart(cache_key, reply.chart_html, html_renderer)
    except Exception:
        logger.exception("EVE HTML 走势图渲染失败，降级为文字回复")
        return [event.plain_result(reply.text)]
    if not rendered:
        return [event.plain_result(reply.text)]
    image = (
        Comp.Image.fromURL(rendered)
        if rendered.startswith(("http://", "https://", "data:"))
        else Comp.Image.fromFileSystem(rendered)
    )
    return [event.chain_result([Comp.Plain(reply.text), image])]


async def html_card_result(
    event,
    label: str,
    query: Callable[..., Awaitable],
    *args,
    html_renderer: Callable[..., Awaitable[str]],
    **kwargs,
):
    """渲染只以图片展示的 HTML 卡片，失败时回退到文字。"""
    try:
        reply = await query(*args, **kwargs)
    except Exception:
        logger.exception("%s查询异常", label)
        return event.plain_result(f"{label}查询出现异常，请稍后重试")
    if not reply.html:
        return event.plain_result(reply.text)
    cache_key = hashlib.sha256(reply.html.encode()).hexdigest()
    try:
        rendered = await _render_chart(cache_key, reply.html, html_renderer)
    except Exception:
        logger.exception("%s HTML 卡片渲染失败，降级为文字回复", label)
        return event.plain_result(reply.text)
    if not rendered:
        return event.plain_result(reply.text)
    import astrbot.api.message_components as Comp

    image = (
        Comp.Image.fromURL(rendered)
        if rendered.startswith(("http://", "https://", "data:"))
        else Comp.Image.fromFileSystem(rendered)
    )
    return event.chain_result([image])


async def _render_chart(
    cache_key: str,
    chart_html: str,
    html_renderer: Callable[..., Awaitable[str]],
) -> str:
    cached = _chart_render_cache.get(cache_key)
    rendered = cached[1] if cached and cached[0] > time.monotonic() else ""
    if rendered and not rendered.startswith(("http://", "https://", "data:")):
        if not Path(rendered).is_file():
            rendered = ""
    if rendered:
        return rendered

    task = _chart_render_flights.get(cache_key)
    if task is None:
        task = asyncio.create_task(_render_chart_once(cache_key, chart_html, html_renderer))
        _chart_render_flights[cache_key] = task
    try:
        return await asyncio.shield(task)
    finally:
        if task.done() and _chart_render_flights.get(cache_key) is task:
            _chart_render_flights.pop(cache_key, None)


async def _render_chart_once(
    cache_key: str,
    chart_html: str,
    html_renderer: Callable[..., Awaitable[str]],
) -> str:
    rendered = await html_renderer(
        chart_html,
        {},
        # Download the rendered image to AstrBot's local temp directory.  Returning
        # the public T2I URL makes the downstream platform fetch a short-lived URL
        # itself; some OneBot deployments cannot reach it and silently drop the image.
        return_url=False,
        options={"type": "png", "full_page": True, "omit_background": True},
    )
    if not rendered:
        return ""
    rendered = str(rendered)
    if len(_chart_render_cache) >= 128:
        now = time.monotonic()
        expired = [key for key, (expires, _) in _chart_render_cache.items() if expires <= now]
        for key in expired or [next(iter(_chart_render_cache))]:
            _chart_render_cache.pop(key, None)
    _chart_render_cache[cache_key] = (
        time.monotonic() + _CHART_RENDER_CACHE_SECONDS,
        rendered,
    )
    return rendered
