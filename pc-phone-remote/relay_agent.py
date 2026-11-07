from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from app import COMMANDS, run_command
from companion import Companion, FeatureError, MAX_BODY, load_config


def request_json(url: str, token: str, payload: dict[str, object] | None = None, timeout: int = 35) -> dict[str, object]:
    data = None
    headers = {"X-Agent-Token": token}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise ValueError("Relay response too large")
        body = body.decode("utf-8")
        return json.loads(body) if body else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="PC Phone Remote relay agent")
    parser.add_argument("--relay-url", default=os.environ.get("RELAY_URL", "").rstrip("/"))
    parser.add_argument("--agent-token", default=os.environ.get("RELAY_AGENT_TOKEN", ""))
    parser.add_argument("--interval", type=float, default=float(os.environ.get("RELAY_POLL_INTERVAL", "1.5")))
    args = parser.parse_args()

    if not args.relay_url:
        print("Set RELAY_URL, for example: https://your-relay.example.com")
        return 2
    if not args.agent_token:
        print("Set RELAY_AGENT_TOKEN to the same token used by relay_server.py")
        return 2

    companion = Companion(load_config(), run_command)
    print("Relay agent started.")
    while True:
        try:
            poll_url = f"{args.relay_url}/agent/poll"
            payload = request_json(poll_url, args.agent_token)
            queued = payload.get("command")
            if not queued:
                continue

            if not isinstance(queued, dict):
                continue

            command_id = queued.get("id")
            try:
                if queued.get("expires_at", 0) <= time.time():
                    raise FeatureError("Job expired", 410)
                data = companion.dispatch(queued.get("payload"))
                result = {"id": command_id, "ok": True, "data": data}
            except FeatureError as exc:
                result = {"id": command_id, "ok": False, "status": exc.status, "message": str(exc)}
            except Exception:
                result = {"id": command_id, "ok": False, "status": 500, "message": "PC operation failed"}

            request_json(f"{args.relay_url}/agent/result", args.agent_token, result, timeout=10)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            print(f"Relay agent error: {exc}")
            time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
