#!/usr/bin/env python3
"""Feishu bot -> local free-model gateway (sandbox-1). Stdlib only.

Listens on 0.0.0.0:$PORT (default 18080).
- POST /feishu/events : Feishu url_verification + im.message.receive_v1
- GET  /health        : {"ok": true, ...}

Env (read from ~/feishu-bot/.env when started by start-ai-stack.sh):
  FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_VERIFY_TOKEN
  GATEWAY_URL (default http://127.0.0.1:18900/v1)
  OPENROUTER_API_KEY (fallback; if unset, read from ~/.hermes/.env)
  PORT (default 18080)
  DEFAULT_MODEL (default nvidia/nemotron-3-ultra-550b-a55b:free)
  MODELS_FILE (default ~/free-models.json)

Rules (from unified workflow branch G):
- Only call a model ID verified free in a scan no older than 24h.
- Never call an ID missing the ':free' suffix (that routes to the paid variant).
- Sensitive content (passwords, verification codes, IDs, payment info) is
  never sent to external models; the bot reminds the user and refuses it.
"""

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOME = Path.home()
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_VERIFY_TOKEN = os.environ.get("FEISHU_VERIFY_TOKEN", "")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://127.0.0.1:18900/v1").rstrip("/")
PORT = int(os.environ.get("PORT", "18080"))
DEFAULT_MODEL = os.environ.get(
    "DEFAULT_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
MODELS_FILE = Path(os.environ.get("MODELS_FILE", str(HOME / "free-models.json")))
OPENROUTER_API = "https://openrouter.ai/api/v1"
SYSTEM_PROMPT = (
    "你是一个 helpful 的 AI 助手，正在通过飞书和用户对话。回答用中文，简洁、说人话，"
    "有不确定的就明说，不要编造事实、数据和链接。"
    "如果用户发来密码、验证码、证件号码、支付信息等敏感内容，提醒对方不要在聊天里发敏感信息，"
    "并拒绝处理该内容。"
)

# ---- state -----------------------------------------------------------------
_chat_model = {}          # chat_id -> model id
_history = {}             # chat_id -> [{"role": ..., "content": ...}] (last 10 turns)
_free_cache = {"checked_at": 0.0, "free_ids": set()}
_token_cache = {"token": "", "expire_at": 0.0}
_lock = threading.Lock()


def log(*args):
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), *args, flush=True)


# ---- credentials (machine-local only, never printed) ------------------------
def _read_env_file(path, key):
    try:
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def gateway_key():
    try:
        data = json.loads((HOME / ".our-free-model" / "settings.json").read_text())
        return data.get("forwardKey", "")
    except (OSError, ValueError):
        return ""


def openrouter_key():
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if key:
        return key
    return _read_env_file(HOME / ".hermes" / ".env", "OPENROUTER_API_KEY")


# ---- free-model radar (fail-closed) ----------------------------------------
def _is_free_entry(m):
    p = m.get("pricing") or {}

    def zero(v):
        try:
            return float(v) == 0
        except (ValueError, TypeError):
            return False

    if not (zero(p.get("prompt")) and zero(p.get("completion"))):
        return False
    return all(zero(p[k]) for k in ("request", "input_cache_read", "input_cache_write")
               if k in p)


def refresh_free_list():
    """Fetch OpenRouter public /models (no key) and rebuild the free set."""
    req = urllib.request.Request(
        OPENROUTER_API + "/models",
        headers={"User-Agent": "FreeToken-Radar/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.load(resp)
    free_ids = {m["id"] for m in raw.get("data", []) if _is_free_entry(m)}
    # Merge the local registry file (gateway list + verified snapshot).
    try:
        reg = json.loads(MODELS_FILE.read_text())
        for item in reg.get("openrouter_free", []) + reg.get("gateway_models", []):
            if isinstance(item, str):
                free_ids.add(item)
    except (OSError, ValueError):
        pass
    with _lock:
        _free_cache["checked_at"] = time.time()
        _free_cache["free_ids"] = free_ids
    return free_ids


def free_ids():
    with _lock:
        age = time.time() - _free_cache["checked_at"]
        ids = set(_free_cache["free_ids"])
    if age > 24 * 3600 or not ids:
        try:
            return refresh_free_list()
        except Exception as exc:  # noqa: BLE001 - fail closed on stale list
            log("free-list refresh failed:", exc)
            if age > 24 * 3600 or not ids:
                return set()
    return ids


def resolve_model(requested):
    """Fail-closed: return a verified-free exact ID, or raise ValueError."""
    requested = (requested or "").strip()
    known = free_ids()
    if not known:
        raise ValueError("免费名单过期或拉取失败，暂不调用任何模型，请稍后再试。")
    if requested in known:
        return requested
    suffixed = requested if requested.endswith(":free") else requested + ":free"
    if suffixed in known:
        log("WARNING: %s not verified-free; using %s" % (requested, suffixed))
        return suffixed
    raise ValueError("“%s”不在最新核实的免费名单里，调不了（缺 :free 后缀会走到付费版）。"
                     "发“模型列表”看今天能用的。" % requested)


# ---- model calls ------------------------------------------------------------
def _post_json(url, payload, key=None, timeout=120):
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, headers=headers,
                                 data=json.dumps(payload).encode())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def call_model(model, messages):
    """Gateway first, OpenRouter direct as fallback. Returns (text, via)."""
    payload = {"model": model, "messages": messages,
               "max_tokens": 1024, "temperature": 0.7}
    gkey = gateway_key()
    if gkey:
        try:
            result = _post_json(GATEWAY_URL + "/chat/completions", payload, gkey)
            if result.get("choices"):
                return result["choices"][0]["message"]["content"], "本地网关"
            if result.get("error"):
                log("gateway error:", str(result["error"])[:200])
        except Exception as exc:  # noqa: BLE001
            log("gateway call failed:", exc)
    okey = openrouter_key()
    if okey:
        try:
            result = _post_json(OPENROUTER_API + "/chat/completions", payload, okey,
                                timeout=150)
            if result.get("choices"):
                return result["choices"][0]["message"]["content"], "OpenRouter 直连"
            if result.get("error"):
                return ("这次没答出来：%s" % str(result["error"])[:200], "OpenRouter 直连")
        except Exception as exc:  # noqa: BLE001
            log("openrouter call failed:", exc)
    return ("网关和 OpenRouter 都没接通，请稍后再试。", "无")


SENSITIVE_PATTERNS = [
    re.compile(r"(密码|passwd|password)\s*[：:=]\s*\S+", re.I),
    re.compile(r"(验证码|verification code|otp)\s*[：:=]?\s*\d{4,8}", re.I),
    re.compile(r"\b\d{15,19}\b"),  # bank-card-like runs
    re.compile(r"(身份证|id card)\s*[：:=]?\s*\d{17}[\dXx]", re.I),
]


def looks_sensitive(text):
    return any(p.search(text) for p in SENSITIVE_PATTERNS)


# ---- Feishu API -------------------------------------------------------------
def tenant_token():
    with _lock:
        if _token_cache["token"] and time.time() < _token_cache["expire_at"]:
            return _token_cache["token"]
    result = _post_json(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=20)
    token = result.get("tenant_access_token", "")
    expire = int(result.get("expire", 0) or 0)
    with _lock:
        _token_cache["token"] = token
        _token_cache["expire_at"] = time.time() + max(expire - 60, 60)
    return token


def reply_message(message_id, text):
    if len(text) > 3500:
        text = text[:3500] + "\n……（回答太长，只显示前面部分）"
    _post_json(
        "https://open.feishu.cn/open-apis/im/v1/messages/%s/reply" % message_id,
        {"msg_type": "text", "content": json.dumps({"text": text}, ensure_ascii=False)},
        key=tenant_token(), timeout=20)


# ---- message handling -------------------------------------------------------
def handle_text(chat_id, message_id, text):
    text = (text or "").strip()
    if not text:
        return
    if looks_sensitive(text):
        reply_message(message_id,
                      "这条我不能处理：里面像是密码、验证码、证件或支付信息，别在聊天里发敏感信息，"
                      "发了也会被发到外面的免费模型那里。换个不带敏感内容的问题再问我吧。")
        return
    if text in ("帮助", "help", "怎么用"):
        reply_message(message_id,
                      "我是你云服务器上的免费模型助手。直接发问题就能聊；\n"
                      "“换模型 <模型ID>”切换模型；“模型列表”看今天能用的免费模型；"
                      "“状态”看当前模型和网关。\n注意：机器是手动恢复的，停了我就回不了话，恢复机器、跑一下启动脚本就能继续聊。")
        return
    if text in ("模型列表", "模型", "有哪些模型"):
        ids = sorted(free_ids())
        reply_message(message_id, "今天能用的免费模型（%d 个，名单每天会变）：\n%s" %
                      (len(ids), "\n".join("· " + i for i in ids[:40])))
        return
    if text == "状态":
        try:
            with urllib.request.urlopen(GATEWAY_URL.replace("/v1", "") + "/health",
                                        timeout=10) as resp:
                gw = "正常" if json.load(resp).get("ok") else "异常"
        except Exception:  # noqa: BLE001
            gw = "不通"
        reply_message(message_id, "当前模型：%s\n本地网关：%s\n想换模型就发“换模型 <模型ID>”。"
                      % (_chat_model.get(chat_id, DEFAULT_MODEL), gw))
        return
    if text.startswith("换模型"):
        wanted = text[3:].strip()
        try:
            model = resolve_model(wanted)
        except ValueError as exc:
            reply_message(message_id, str(exc))
            return
        _chat_model[chat_id] = model
        reply_message(message_id, "已切换到 %s，发问题就能聊。" % model)
        return
    # Normal chat turn.
    model = _chat_model.get(chat_id, DEFAULT_MODEL)
    try:
        model = resolve_model(model)
    except ValueError as exc:
        reply_message(message_id, str(exc))
        return
    hist = _history.setdefault(chat_id, [])
    hist.append({"role": "user", "content": text})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + hist[-10:]
    answer, via = call_model(model, messages)
    hist.append({"role": "assistant", "content": answer})
    _history[chat_id] = hist[-10:]
    reply_message(message_id, answer)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep stdout clean
        pass

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/health"):
            gw = "unknown"
            try:
                with urllib.request.urlopen(
                        GATEWAY_URL.replace("/v1", "") + "/health", timeout=5) as resp:
                    gw = "ok" if json.load(resp).get("ok") else "bad"
            except Exception:  # noqa: BLE001
                gw = "down"
            self._send(200, {"ok": True, "model": DEFAULT_MODEL, "gateway": gw})
        else:
            self._send(404, {"ok": False})

    def do_POST(self):
        if self.path != "/feishu/events":
            self._send(404, {"ok": False})
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._send(400, {"ok": False})
            return
        # Feishu URL verification challenge.
        if body.get("type") == "url_verification":
            self._send(200, {"challenge": body.get("challenge", "")})
            return
        header = body.get("header", {}) or {}
        if FEISHU_VERIFY_TOKEN and header.get("token") not in ("", FEISHU_VERIFY_TOKEN):
            log("event token mismatch, ignored")
            self._send(200, {"ok": True})
            return
        if header.get("event_type") == "im.message.receive_v1":
            event = body.get("event", {}) or {}
            sender = event.get("sender", {}) or {}
            if sender.get("sender_type") == "app":
                self._send(200, {"ok": True})
                return
            message = event.get("message", {}) or {}
            if message.get("message_type") != "text":
                self._send(200, {"ok": True})
                return
            try:
                content = json.loads(message.get("content", "{}"))
                text = content.get("text", "")
            except ValueError:
                text = ""
            chat_id = message.get("chat_id", "")
            message_id = message.get("message_id", "")
            threading.Thread(target=handle_text, args=(chat_id, message_id, text),
                             daemon=True).start()
        self._send(200, {"ok": True})


def main():
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        raise SystemExit("FEISHU_APP_ID / FEISHU_APP_SECRET not set; refusing to start.")
    refresh_free_list()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    log("feishu bot listening on 0.0.0.0:%d, default model %s" % (PORT, DEFAULT_MODEL))
    server.serve_forever()


if __name__ == "__main__":
    main()
