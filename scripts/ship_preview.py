#!/usr/bin/env python3
"""Preview the live EVE ship card at /eve-ship-card-preview.html."""

from __future__ import annotations

import argparse
import html
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plugin.features.ship.client import ShipClient  # noqa: E402
from plugin.features.ship.renderer import ShipCardRenderer  # noqa: E402


class ShipPreviewHandler(BaseHTTPRequestHandler):
    client = ShipClient()
    renderer = ShipCardRenderer()

    def do_GET(self) -> None:  # noqa: N802
        url = urlsplit(self.path)
        name = parse_qs(url.query).get("name", ["乌鸦级"])[0].strip()[:100]
        if url.path == "/card":
            if not name:
                self.send_error(HTTPStatus.BAD_REQUEST, "请输入舰船名称")
                return
            try:
                card = self.renderer.render(self.client.query(name))
            except ValueError as error:
                self._send_html(
                    f'<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                    f'<body style="margin:0;padding:24px;background:#182128;color:#e8edf2;'
                    f'font:14px sans-serif">{html.escape(str(error))}</body></html>'
                )
                return
            except Exception as error:
                self.send_error(HTTPStatus.BAD_GATEWAY, str(error))
                return
            self._send_html(card)
            return
        if url.path not in {"/", "/eve-ship-card-preview.html"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        safe_name = html.escape(name, quote=True)
        card_url = f"/card?name={quote(name)}"
        self._send_html(
            f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>EVE 舰船资料预览</title>
<style>*{{box-sizing:border-box}}body{{margin:0;padding:32px 16px;background:#0b1115;color:#e8edf2;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif}}
main{{max-width:660px;margin:0 auto}}form{{display:flex;gap:8px;margin-bottom:18px}}input{{min-width:0;flex:1;padding:11px 13px;border:1px solid #34424c;border-radius:7px;background:#172129;color:#e8edf2;font:inherit}}
button{{padding:11px 20px;border:0;border-radius:7px;background:#c7a862;color:#14191c;font:inherit;font-weight:700;cursor:pointer}}iframe{{display:block;width:100%;height:950px;border:0;background:transparent}}</style>
</head><body><main><form action="/eve-ship-card-preview.html"><input name="name" value="{safe_name}" placeholder="输入舰船名称" aria-label="舰船名称"><button>查询</button></form>
<iframe title="舰船资料卡片" src="{html.escape(card_url, quote=True)}" onload="try{{this.style.height=this.contentDocument.body.scrollHeight+'px'}}catch(e){{}}"></iframe></main></body></html>"""
        )

    def _send_html(self, markup: str) -> None:
        content = markup.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main() -> None:
    parser = argparse.ArgumentParser(description="使用真实接口预览 EVE 舰船资料卡片")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8766, type=int)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ShipPreviewHandler)
    print(f"舰船资料预览：http://{args.host}:{args.port}/eve-ship-card-preview.html", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
