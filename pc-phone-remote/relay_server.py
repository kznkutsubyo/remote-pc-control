"""Single-PC relay. HTTPS termination is provided by the hosting proxy."""
from __future__ import annotations

import argparse
import os
import secrets
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse

from app import RemoteHandler
from companion import ACTIONS, FeatureError


class Broker:
    def __init__(self, timeout=22):
        self.condition = threading.Condition()
        self.pending = {}
        self.timeout = timeout

    def submit(self, payload):
        identifier = secrets.token_urlsafe(18)
        job = {"id": identifier, "payload": payload, "expires_at": time.time() + self.timeout,
               "event": threading.Event(), "result": None, "claimed": False}
        with self.condition:
            if len(self.pending) >= 4:
                raise FeatureError("Relay is busy. Try again shortly.", 429)
            self.pending[identifier] = job
            self.condition.notify_all()
        try:
            if not job["event"].wait(self.timeout):
                raise FeatureError("PC did not reply. Check the agent; the action may have completed if the reply was lost.", 504)
            result = job["result"]
            if not result.get("ok"):
                status = result.get("status", 500)
                raise FeatureError(result.get("message", "PC operation failed"), status if type(status) is int and 400 <= status <= 599 else 500)
            return result.get("data", {})
        finally:
            with self.condition:
                self.pending.pop(identifier, None)

    def poll(self, timeout=20):
        deadline = time.monotonic() + timeout
        with self.condition:
            while time.monotonic() < deadline:
                for job in self.pending.values():
                    if not job["claimed"] and job["expires_at"] > time.time():
                        job["claimed"] = True
                        return {key: job[key] for key in ("id", "payload", "expires_at")}
                self.condition.wait(max(0, deadline - time.monotonic()))
        return None

    def finish(self, result):
        with self.condition:
            identifier = result.get("id")
            if not isinstance(identifier, str):
                raise FeatureError("Invalid job ID")
            job = self.pending.get(identifier)
            if job is None or not job["claimed"] or job["event"].is_set():
                raise FeatureError("Job expired or already completed", 410)
            job["result"] = result
            job["event"].set()


class RelayHandler(RemoteHandler):
    server_version = "PCPhoneRelay/2.0"

    def agent_allowed(self):
        token = self.headers.get("X-Agent-Token", "")
        return bool(token) and secrets.compare_digest(token.encode(), self.server.agent_token.encode())

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self.send_bytes(200, b"ok", "text/plain")
        elif path == "/agent/poll":
            if not self.agent_allowed():
                self.send_json(401, {"message": "Invalid agent token"})
                return
            self.send_json(200, {"command": self.server.broker.poll()})
        else:
            self.send_json(404, {"message": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/login":
            return super().do_POST()
        if path not in {"/api/v2", "/api/command", "/agent/result"}:
            self.send_json(404, {"message": "Not found"})
            return
        allowed = self.agent_allowed() if path == "/agent/result" else self.is_authenticated()
        if not allowed:
            self.send_json(401, {"message": "Not authenticated"})
            return
        try:
            payload = self.api_request()
            if path == "/agent/result":
                self.server.broker.finish(payload)
                self.send_json(200, {"received": True})
                return
            if path == "/api/command":
                payload = {"action": "command", "command": payload.get("command")}
            if not isinstance(payload.get("action"), str) or payload["action"] not in ACTIONS:
                raise FeatureError("Unsupported action")
            self.send_json(200, self.server.broker.submit(payload))
        except FeatureError as exc:
            self.send_json(exc.status, {"message": str(exc)})


def main():
    parser = argparse.ArgumentParser(description="PC Phone Remote relay server")
    parser.add_argument("--host", default=os.environ.get("RELAY_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("RELAY_PORT", "8080")))
    parser.add_argument("--pin", default=os.environ.get("RELAY_PIN", ""))
    parser.add_argument("--agent-token", default=os.environ.get("RELAY_AGENT_TOKEN", ""))
    args = parser.parse_args()
    if not args.pin or len(args.agent_token) < 24:
        parser.error("Set RELAY_PIN and a RELAY_AGENT_TOKEN of at least 24 characters")
    server = ThreadingHTTPServer((args.host, args.port), RelayHandler)
    server.pin = args.pin
    server.agent_token = args.agent_token
    server.broker = Broker()
    print(f"Relay listening on port {args.port}; update both the PC agent and Android app to v2.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
