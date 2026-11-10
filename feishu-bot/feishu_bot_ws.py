#!/usr/bin/env python3
"""Feishu bot (long-connection / WebSocket edition).

Same brain as feishu_bot.py (free-model radar, model calls, sensitive filter,
multi-turn history) but receives events over Feishu's WebSocket long connection
instead of an HTTP callback URL. That is the Cruxine video's method and the
mode Feishu itself marks "(推荐)" on the event page: the bot dials out to
Feishu, so no inbound delivery to a public URL is needed at all.

Env (same .env as feishu_bot.py):
  FEISHU_APP_ID, FEISHU_APP_SECRET
  GATEWAY_URL, OPENROUTER_API_KEY, PORT (health endpoint, default 18080)
  DEFAULT_MODEL, MODELS_FILE

Needs: pip install lark-oapi
Run: python feishu_bot_ws.py   (blocks on ws.start(), auto-reconnect on)
"""

import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import lark_oapi as lark
from lark_oapi.ws import Client as WSClient

from feishu_bot import (  # noqa: F401  (reuse the proven brain)
    DEFAULT_MODEL, FEISHU_APP_ID, FEISHU_APP_SECRET, GATEWAY_URL, PORT,
    handle_text, log, refresh_free_list,
)


def on_message(data):
    """lark_oapi event handler for P2ImMessageReceiveV1."""
    log("ws frame dispatched to handler, type=%s" % type(data).__name__)
    try:
        event = data.event
        message = event.message
        sender = event.sender
        if sender is not None and sender.sender_type == "app":
            return
        if message is None or message.message_type != "text":
            return
        try:
            text = json.loads(message.content or "{}").get("text", "")
        except ValueError:
            text = ""
        log("ws event: chat=%s msg=%s text=%.40s"
            % (message.chat_id, message.message_id, text))
        threading.Thread(
            target=handle_text,
            args=(message.chat_id, message.message_id, text),
            daemon=True).start()
    except Exception as exc:  # noqa: BLE001 - never kill the ws loop
        log("on_message failed:", exc)


class HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path in ("/", "/health"):
            gw = "unknown"
            try:
                with urllib.request.urlopen(
                        GATEWAY_URL.replace("/v1", "") + "/health", timeout=5) as resp:
                    gw = "ok" if json.load(resp).get("ok") else "bad"
            except Exception:  # noqa: BLE001
                gw = "down"
            body = json.dumps({"ok": True, "model": DEFAULT_MODEL,
                               "gateway": gw, "mode": "websocket"},
                              ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


def main():
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        raise SystemExit("FEISHU_APP_ID / FEISHU_APP_SECRET not set; refusing to start.")
    try:
        refresh_free_list()
    except Exception as exc:  # noqa: BLE001 - start anyway; free_ids() retries per message
        log("free-list refresh at startup failed (will retry on first message):", exc)
    threading.Thread(
        target=ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever,
        daemon=True).start()
    log("health endpoint on 0.0.0.0:%d, default model %s" % (PORT, DEFAULT_MODEL))
    handler = (lark.EventDispatcherHandler.builder("", "")
               .register_p2_im_message_receive_v1(on_message)
               .build())
    ws = WSClient(FEISHU_APP_ID, FEISHU_APP_SECRET,
                  event_handler=handler,
                  domain=lark.FEISHU_DOMAIN,
                  log_level=lark.LogLevel.DEBUG,
                  auto_reconnect=True)
    log("starting websocket long connection to Feishu ...")
    ws.start()  # blocks; reconnects automatically


if __name__ == "__main__":
    main()
