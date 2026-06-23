from __future__ import annotations

import argparse
import http.cookies
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


DEFAULT_PIN = ""
SESSION_COOKIE = "pc_remote_relay_session"
COMMANDS = {"mute", "lock", "sleep", "restart", "shutdown"}

SESSIONS: dict[str, float] = {}
QUEUE: list[dict[str, object]] = []
RESULTS: list[dict[str, object]] = []
LOCK = threading.Lock()


def json_bytes(payload: object) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


class RelayHandler(BaseHTTPRequestHandler):
    server_version = "PCPhoneRemoteRelay/1.0"

    @property
    def pin(self) -> str:
        return self.server.pin  # type: ignore[attr-defined]

    @property
    def agent_token(self) -> str:
        return self.server.agent_token  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] {self.client_address[0]} - {fmt % args}")

    def send_payload(self, status: int, payload: object, content_type: str = "application/json") -> None:
        content = payload if isinstance(payload, bytes) else json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def is_authenticated(self) -> bool:
        cookies = http.cookies.SimpleCookie()
        cookies.load(self.headers.get("Cookie", ""))
        token_cookie = cookies.get(SESSION_COOKIE)
        if token_cookie is None:
            return False

        with LOCK:
            expires_at = SESSIONS.get(token_cookie.value)
            if not expires_at or expires_at < time.time():
                SESSIONS.pop(token_cookie.value, None)
                return False

            SESSIONS[token_cookie.value] = time.time() + 60 * 60 * 12
            return True

    def agent_allowed(self) -> bool:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        header_token = self.headers.get("X-Agent-Token", "")
        query_token = query.get("token", [""])[0]
        return secrets.compare_digest(header_token or query_token, self.agent_token)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            self.send_payload(200, b"ok", "text/plain; charset=utf-8")
            return

        if parsed.path == "/agent/poll":
            if not self.agent_allowed():
                self.send_payload(401, {"message": "bad agent token"})
                return

            deadline = time.time() + 25
            command = None
            while time.time() < deadline:
                with LOCK:
                    if QUEUE:
                        command = QUEUE.pop(0)
                        break
                time.sleep(0.5)

            self.send_payload(200, {"command": command})
            return

        if parsed.path == "/agent/results":
            if not self.agent_allowed():
                self.send_payload(401, {"message": "bad agent token"})
                return

            with LOCK:
                payload = {"results": RESULTS[-20:]}
            self.send_payload(200, payload)
            return

        self.send_payload(404, {"message": "not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)

        if parsed.path == "/login":
            form = parse_qs(body.decode("utf-8", errors="replace"))
            if form.get("pin", [""])[0] != self.pin:
                self.send_payload(403, {"message": "wrong pin"})
                return

            token = secrets.token_urlsafe(32)
            with LOCK:
                SESSIONS[token] = time.time() + 60 * 60 * 12

            content = json_bytes({"message": "logged in"})
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if parsed.path == "/api/command":
            if not self.is_authenticated():
                self.send_payload(401, {"message": "not authenticated"})
                return

            try:
                payload = json.loads(body.decode("utf-8"))
                command = payload.get("command")
            except (json.JSONDecodeError, UnicodeDecodeError):
                command = None

            if command not in COMMANDS:
                self.send_payload(400, {"message": "unknown command"})
                return

            queued = {
                "id": secrets.token_urlsafe(12),
                "command": command,
                "created_at": int(time.time()),
            }
            with LOCK:
                QUEUE.append(queued)

            self.send_payload(200, {"message": f"{command} queued", "queued": queued})
            return

        if parsed.path == "/agent/result":
            if not self.agent_allowed():
                self.send_payload(401, {"message": "bad agent token"})
                return

            try:
                payload = json.loads(body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = {}

            payload["received_at"] = int(time.time())
            with LOCK:
                RESULTS.append(payload)
                del RESULTS[:-100]

            self.send_payload(200, {"message": "result saved"})
            return

        self.send_payload(404, {"message": "not found"})


def main() -> int:
    parser = argparse.ArgumentParser(description="PC Phone Remote relay server")
    parser.add_argument("--host", default=os.environ.get("RELAY_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("RELAY_PORT", "8080")))
    parser.add_argument("--pin", default=os.environ.get("RELAY_PIN", DEFAULT_PIN))
    parser.add_argument("--agent-token", default=os.environ.get("RELAY_AGENT_TOKEN", "change-this-agent-token"))
    args = parser.parse_args()

    if args.agent_token == "change-this-agent-token":
        print("WARNING: set RELAY_AGENT_TOKEN to a long random value before exposing this server.")

    server = ThreadingHTTPServer((args.host, args.port), RelayHandler)
    server.pin = args.pin  # type: ignore[attr-defined]
    server.agent_token = args.agent_token  # type: ignore[attr-defined]

    print(f"Relay server listening on http://{args.host}:{args.port}")
    print("Phone uses /login and /api/command. PC agent uses /agent/poll.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
