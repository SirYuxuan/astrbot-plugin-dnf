#!/usr/bin/env python3
"""Run the EVE command feature locally with the real SDE and Fuzzwork market data."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plugin.features.eve.catalog import EveCatalog  # noqa: E402
from plugin.features.eve.chart import PriceChartRenderer  # noqa: E402
from plugin.features.eve.client import (  # noqa: E402
    Adam4EveHistoryClient,
    EveMarketClient,
    FuzzworkMarketClient,
    MemoryOrderCache,
    RedisOrderCache,
)
from plugin.features.eve.sde import SdeUpdater  # noqa: E402
from plugin.features.eve.service import EveFeature  # noqa: E402

PREVIEW_PAGE = ROOT / "docs" / "eve-query-preview.html"


class PreviewApp:
    def __init__(self, data_dir: Path, redis_url: str, refresh_sde: bool):
        data_dir.mkdir(parents=True, exist_ok=True)
        catalog = EveCatalog(data_dir / "eve.db")
        user_agent = (
            "astrbot-plugin-dnf/1.6 preview (+https://github.com/SirYuxuan/astrbot-plugin-dnf)"
        )
        updater = SdeUpdater(catalog, timeout=300, user_agent=user_agent)
        status = catalog.status()
        if refresh_sde or not status["count"]:
            print("正在从 CCP 下载并构建 Tranquility SDE 名称库，首次运行需要一些时间……")
            build, count, changed = updater.update(force=refresh_sde)
            action = "已更新" if changed else "无需更新"
            print(f"SDE {build} {action}，共 {count} 个类型。")
        else:
            print(f"使用本地 SDE {status['build']}，共 {status['count']} 个类型。")

        cache = (
            RedisOrderCache(redis_url, prefix="yuxuandnf:eve:preview")
            if redis_url
            else MemoryOrderCache()
        )
        current_market = FuzzworkMarketClient(
            timeout=30,
            cache_seconds=300,
            user_agent=user_agent,
            cache=cache,
        )
        market = EveMarketClient(
            current_market,
            Adam4EveHistoryClient(
                timeout=30,
                cache_seconds=21600,
                user_agent=user_agent,
                cache=cache,
            ),
        )
        self.chart_pages: dict[str, str] = {}
        self.feature = EveFeature(
            catalog,
            market,
            updater,
            search_result_limit=5,
            chart_renderer=PriceChartRenderer(),
        )

    def query(self, command: str):
        return asyncio.run(self.feature.handle_reply(command))

    def publish_chart(self, markup: str) -> str:
        chart_id = hashlib.sha256(markup.encode()).hexdigest()[:16]
        self.chart_pages[chart_id] = markup
        return f"/charts/{chart_id}.html"


class PreviewHandler(BaseHTTPRequestHandler):
    app: PreviewApp

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path.startswith("/charts/") and path.endswith(".html"):
            chart_id = Path(path).stem
            markup = self.app.chart_pages.get(chart_id)
            if markup:
                content = markup.encode()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if path not in {"/", "/index.html"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = PREVIEW_PAGE.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/query":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(size) or b"{}")
            command = str(payload.get("command", "")).strip()
            if not command:
                raise ValueError("请输入查询命令")
            reply = self.app.query(command)
            payload = {"output": reply.text}
            if reply.chart_html:
                payload["chart"] = self.app.publish_chart(reply.chart_html)
            self._send_json(payload)
        except (ValueError, json.JSONDecodeError) as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except Exception as error:
            self._send_json({"error": f"真实查询失败：{error}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _send_json(self, payload: dict[str, str], status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, message: str, *args: object) -> None:
        print(f"[EVE Preview] {message % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="在网页中真实调用 EVE /jt 查价命令")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=ROOT / ".eve-preview",
        help="SDE 名称数据库目录",
    )
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("EVE_PREVIEW_REDIS_URL", "redis://localhost:6379/0"),
        help="Redis URL；传空字符串可禁用",
    )
    parser.add_argument("--refresh-sde", action="store_true", help="强制更新 CCP SDE")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    app = PreviewApp(args.data_dir, args.redis_url.strip(), args.refresh_sde)
    PreviewHandler.app = app
    server = ThreadingHTTPServer((args.host, args.port), PreviewHandler)
    url = f"http://{args.host}:{args.port}"
    print(f"EVE 查价测试页：{url}")
    print("按 Ctrl+C 停止。")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
