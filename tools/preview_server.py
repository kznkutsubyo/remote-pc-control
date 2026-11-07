"""Loopback-only UI fixture. Never executes Windows commands."""
import sys
from pathlib import Path
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pc-phone-remote"))
from app import RemoteHandler
from companion import Companion

folder = ROOT / "artifacts" / "preview-shared"
folder.mkdir(parents=True, exist_ok=True)
(folder / "Welcome.txt").write_text("File transfer works.\n", "utf-8")
features = Companion({"share_dir": str(folder)}, lambda command: None)


class Fixture(Companion):
    def dispatch(self, payload):
        if payload.get("action") in {"command", "media", "timer.set", "timer.cancel"}:
            return {"sent": True}
        return super().dispatch(payload)


server = ThreadingHTTPServer(("127.0.0.1", 8877), RemoteHandler)
server.pin = "preview-only"
server.companion = Fixture({"share_dir": str(folder)})
print("UI fixture on 127.0.0.1:8877", flush=True)
server.serve_forever()
