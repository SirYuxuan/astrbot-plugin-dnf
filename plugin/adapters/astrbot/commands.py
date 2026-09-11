"""框架事件适配与一致的异常回复，不包含查询、解析或监控逻辑。"""

from collections.abc import Awaitable, Callable

from astrbot.api import logger


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


async def query_result(event, label: str, query: Callable[..., Awaitable[str]], *args, **kwargs):
    try:
        text = await query(*args, **kwargs)
    except Exception:
        logger.exception("%s查询异常", label)
        text = f"{label}查询出现异常，请稍后重试"
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

    try:
        rendered = await html_renderer(
            reply.chart_html,
            {},
            options={"type": "png", "full_page": True, "omit_background": True},
        )
    except Exception:
        logger.exception("EVE HTML 走势图渲染失败，降级为文字回复")
        return [event.plain_result(reply.text)]
    if not rendered:
        return [event.plain_result(reply.text)]
    rendered = str(rendered)
    image = (
        Comp.Image.fromURL(rendered)
        if rendered.startswith(("http://", "https://", "data:"))
        else Comp.Image.fromFileSystem(rendered)
    )
    return [
        event.chain_result(
            [
                Comp.Plain(reply.text),
                image,
            ]
        )
    ]
