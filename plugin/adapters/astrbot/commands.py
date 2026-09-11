"""框架事件适配与一致的异常回复，不包含查询、解析或监控逻辑。"""

from collections.abc import Awaitable, Callable

from astrbot.api import logger


def message_text(event) -> str:
    message = getattr(event, "message_str", None)
    if message is not None:
        return str(message).strip()
    getter = getattr(event, "get_message_str", None)
    return str(getter() if callable(getter) else event).strip()


async def query_result(event, label: str, query: Callable[..., Awaitable[str]], *args):
    try:
        text = await query(*args)
    except Exception:
        logger.exception("%s查询异常", label)
        text = f"{label}查询出现异常，请稍后重试"
    return event.plain_result(text)
