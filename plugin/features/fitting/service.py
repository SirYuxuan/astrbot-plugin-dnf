"""按平台私聊会话和发送者隔离的两步输入流程。"""

import asyncio
import re
import time
from dataclasses import dataclass

import requests

from .client import FittingClient, FittingImportError


@dataclass
class FittingSession:
    expires: float
    character: str = ""


class FittingFeature:
    def __init__(self, client: FittingClient, session_timeout: int = 300):
        self.client = client
        self.session_timeout = max(1, session_timeout)
        self.sessions: dict[tuple[str, str], FittingSession] = {}
        self.pending: set[tuple[str, str]] = set()

    async def handle(
        self, origin: str, qq: str, text: str, *, is_private: bool, start: bool = False
    ) -> str | None:
        if not is_private:
            return "配置导入仅限私聊，请私聊发送 /fitt。" if start else None
        key = (origin, qq)
        text = text.strip()
        session = self.sessions.get(key)
        if not start and session is None and key not in self.pending:
            return None
        if not re.fullmatch(r"[1-9]\d{4,11}", qq) or not origin:
            return "无法获取有效的 QQ 私聊会话。"
        if key in self.pending:
            return "配置正在导入，请等待结果，勿重复提交。"
        if start:
            now = time.monotonic()
            self.sessions = {k: s for k, s in self.sessions.items() if s.expires > now}
            if len(self.sessions) >= 1024 and key not in self.sessions:
                return "当前导入会话过多，请稍后重试。"
            self.sessions[key] = FittingSession(now + self.session_timeout)
            return "请输入角色名\n（发送 /cancel 或“取消”退出，5 分钟无操作后过期）"
        if text in {"/cancel", "取消"}:
            self.sessions.pop(key, None)
            return "已取消配置导入。"
        if text.startswith("/"):
            self.sessions.pop(key, None)
            return None  # 其他指令正常处理，同时终止本次导入。
        if session.expires <= time.monotonic():
            self.sessions.pop(key, None)
            return "配置导入已超时，请重新发送 /fitt。"
        session.expires = time.monotonic() + self.session_timeout
        if not session.character:
            if not text or "\n" in text or len(text) > 100:
                return "请输入有效的角色名（单行文本）。"
            session.character = text
            return "请发送配置\n（完整 EFT 文本，首行为 [舰船名称, 配置名称]）"
        if text.startswith("```") and text.endswith("```"):
            text = text.partition("\n")[2].rsplit("```", 1)[0].strip()
        if len(text) > 100000 or not re.match(r"^\[[^\r\n,]+,[^\r\n]+\]", text):
            return "配置格式无效，请发送完整 EFT 配置，首行为 [舰船名称, 配置名称]。"
        self.sessions.pop(key, None)
        self.pending.add(key)
        try:
            await asyncio.to_thread(self.client.import_fitting, qq, session.character, text)
        except FittingImportError as error:
            return f"配置导入失败：{error}\n可发送 /fitt 重新开始。"
        except requests.RequestException:
            return "配置导入请求异常，结果待确认。请先在游戏中检查配置，避免重复导入。"
        except Exception:
            return "配置导入出现异常，结果待确认。请先在游戏中检查配置。"
        finally:
            self.pending.discard(key)
        return "配置导入成功。"
