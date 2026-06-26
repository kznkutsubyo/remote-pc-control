from __future__ import annotations

import argparse
import html
import http.cookies
import ipaddress
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlencode, urlparse

try:
    import qrcode
    import qrcode.image.svg
except ImportError:
    qrcode = None


APP_NAME = "PC Phone Remote"
DEFAULT_PIN = ""
SESSION_COOKIE = "pc_remote_session"

SESSIONS: dict[str, float] = {}
SESSIONS_LOCK = threading.Lock()


COMMANDS = {
    "mute": {
        "label": "Mute",
        "description": "Toggle system sound",
        "confirm": False,
        "button": "Mute",
    },
    "lock": {
        "label": "Lock",
        "description": "Lock Windows session",
        "confirm": False,
        "button": "Lock",
    },
    "sleep": {
        "label": "Sleep",
        "description": "Put PC to sleep",
        "confirm": True,
        "button": "Sleep",
    },
    "restart": {
        "label": "Restart",
        "description": "Restart immediately",
        "confirm": True,
        "button": "Restart",
    },
    "shutdown": {
        "label": "Shutdown",
        "description": "Turn off immediately",
        "confirm": True,
        "button": "Shutdown",
    },
}

TASK_NAMES = {
    "lock": "PC Phone Remote - Lock",
    "sleep": "PC Phone Remote - Sleep",
    "restart": "PC Phone Remote - Restart",
    "shutdown": "PC Phone Remote - Shutdown",
}


def local_addresses(port: int) -> list[str]:
    addresses = {"127.0.0.1"}
    hostname = socket.gethostname()

    try:
        for item in socket.getaddrinfo(hostname, None, socket.AF_INET):
            addresses.add(item[4][0])
    except OSError:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            addresses.add(sock.getsockname()[0])
    except OSError:
        pass

    return [f"http://{address}:{port}" for address in sorted(addresses)]


def preferred_host(port: int) -> str:
    fallback = f"http://127.0.0.1:{port}"
    for address in local_addresses(port):
        parsed = urlparse(address)
        host = parsed.hostname or ""
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            continue
        if ip.is_private and not ip.is_loopback:
            return address

    for address in local_addresses(port):
        parsed = urlparse(address)
        host = parsed.hostname or ""
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            continue
        if not ip.is_loopback:
            return address

    return fallback


def setup_uri(pin: str, port: int, name: str = "My PC") -> str:
    base = preferred_host(port)
    parsed = urlparse(base)
    query = {
        "name": name,
        "host": parsed.hostname or "",
        "port": str(parsed.port or port),
    }
    if pin:
        query["pin"] = pin
    return "pcphone://add?" + urlencode(query)


def qr_svg_data_uri(value: str) -> str:
    if qrcode is None:
        return ""

    factory = qrcode.image.svg.SvgPathImage
    image = qrcode.make(value, image_factory=factory)
    raw = image.to_string(encoding="unicode")
    return "data:image/svg+xml;charset=utf-8," + quote(raw)


def run_task(command: str) -> bool:
    task_name = TASK_NAMES.get(command)
    if not task_name:
        return False

    completed = subprocess.run(
        ["schtasks.exe", "/Run", "/TN", task_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return completed.returncode == 0


def run_command(command: str) -> None:
    if command == "mute":
        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "(New-Object -ComObject WScript.Shell).SendKeys([char]173)",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    if command == "lock":
        if run_task(command):
            return
        subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])
        return

    if command == "sleep":
        if run_task(command):
            return
        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    if command == "restart":
        if run_task(command):
            return
        subprocess.Popen(["shutdown", "/r", "/t", "0"])
        return

    if command == "shutdown":
        if run_task(command):
            return
        subprocess.Popen(["shutdown", "/s", "/t", "0"])
        return

    raise ValueError(f"Unknown command: {command}")


def page_shell(title: str, body: str) -> bytes:
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #101214;
      --panel: #181c20;
      --text: #f6f7f8;
      --muted: #a9b0b7;
      --line: #2a3036;
      --accent: #48c78e;
      --danger: #ff5d5d;
      --warn: #f5b14c;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}

    * {{ box-sizing: border-box; }}
    body {{
      min-height: 100vh;
      margin: 0;
      display: grid;
      place-items: center;
      background:
        radial-gradient(circle at top left, rgba(72, 199, 142, .18), transparent 34rem),
        linear-gradient(145deg, #101214 0%, #171a1d 55%, #0e1012 100%);
      color: var(--text);
    }}

    main {{
      width: min(100% - 32px, 460px);
      padding: 28px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: color-mix(in srgb, var(--panel) 92%, transparent);
      box-shadow: 0 24px 70px rgba(0, 0, 0, .28);
    }}

    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      line-height: 1.1;
      letter-spacing: 0;
    }}

    p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }}

    form.login {{
      display: grid;
      gap: 14px;
      margin-top: 22px;
    }}

    input {{
      width: 100%;
      min-height: 50px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0 14px;
      background: #0d0f11;
      color: var(--text);
      font: inherit;
    }}

    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 24px;
    }}

    button {{
      min-height: 74px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #20262b;
      color: var(--text);
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      touch-action: manipulation;
    }}

    button span {{
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 500;
      line-height: 1.25;
    }}

    button:hover, button:focus-visible {{
      border-color: var(--accent);
      outline: none;
    }}

    .primary {{
      min-height: 52px;
      background: var(--accent);
      color: #06110c;
      border-color: transparent;
    }}

    .wide {{ grid-column: 1 / -1; }}
    .warn {{ border-color: color-mix(in srgb, var(--warn) 60%, var(--line)); }}
    .danger {{ border-color: color-mix(in srgb, var(--danger) 70%, var(--line)); }}

    .status {{
      min-height: 22px;
      margin-top: 16px;
      color: var(--muted);
      font-size: 14px;
    }}

    .error {{
      margin-top: 14px;
      color: #ff9b9b;
    }}

    @media (max-width: 380px) {{
      main {{ padding: 22px; }}
      .grid {{ grid-template-columns: 1fr; }}
      .wide {{ grid-column: auto; }}
    }}
  </style>
</head>
<body>
  <main>{body}</main>
</body>
</html>"""
    return document.encode("utf-8")


def login_page(error: str = "") -> bytes:
    message = f'<p class="error">{html.escape(error)}</p>' if error else ""
    return page_shell(
        APP_NAME,
        f"""
        <h1>{APP_NAME}</h1>
        <p>Enter the PIN from your PC to control basic power and sound actions.</p>
        <form class="login" method="post" action="/login">
          <input name="pin" type="password" inputmode="numeric" autocomplete="current-password" placeholder="PIN" autofocus>
          <button class="primary" type="submit">Connect</button>
        </form>
        {message}
        """,
    )


def remote_page() -> bytes:
    buttons = []
    for key, item in COMMANDS.items():
        classes = []
        if key == "mute":
            classes.append("wide")
        if key in {"sleep", "restart"}:
            classes.append("warn")
        if key == "shutdown":
            classes.append("danger")
        confirm = "true" if item["confirm"] else "false"
        buttons.append(
            f"""
            <button class="{' '.join(classes)}" data-command="{key}" data-confirm="{confirm}">
              {html.escape(item["button"])}
              <span>{html.escape(item["description"])}</span>
            </button>
            """
        )

    return page_shell(
        APP_NAME,
        f"""
        <h1>{APP_NAME}</h1>
        <p>Connected to this Windows PC.</p>
        <section class="grid">
          {''.join(buttons)}
        </section>
        <p id="status" class="status"></p>
        <script>
          const status = document.querySelector("#status");
          document.querySelectorAll("[data-command]").forEach((button) => {{
            button.addEventListener("click", async () => {{
              const command = button.dataset.command;
              if (button.dataset.confirm === "true" && !confirm(`Run ${{button.textContent.trim().split("\\n")[0]}}?`)) {{
                return;
              }}

              status.textContent = "Sending...";
              button.disabled = true;

              try {{
                const response = await fetch("/api/command", {{
                  method: "POST",
                  headers: {{ "Content-Type": "application/json" }},
                  body: JSON.stringify({{ command }}),
                }});
                const payload = await response.json();
                status.textContent = payload.message || "Done";
              }} catch (error) {{
                status.textContent = "Could not reach the PC.";
              }} finally {{
                setTimeout(() => button.disabled = false, 650);
              }}
            }});
          }});
        </script>
        """,
    )


def pair_page(pin: str, port: int) -> bytes:
    uri = setup_uri(pin, port)
    qr_src = qr_svg_data_uri(uri)
    qr_block = (
        f'<img alt="Pairing QR code" src="{qr_src}" style="width: min(100%, 280px); display: block; margin: 22px auto; background: white; padding: 14px; border-radius: 8px;">'
        if qr_src
        else '<p class="status">Install optional dependencies to show a QR code: <code>pip install -r requirements.txt</code></p>'
    )
    return page_shell(
        f"{APP_NAME} Pairing",
        f"""
        <h1>Pair this PC</h1>
        <p>Scan the QR code with your phone camera, copy the setup code, then paste it in the Android app: Devices -> Import setup.</p>
        {qr_block}
        <p class="status">Setup code:</p>
        <input value="{html.escape(uri)}" readonly onclick="this.select()">
        <p class="status">Local address: {html.escape(preferred_host(port))}</p>
        """,
    )


class RemoteHandler(BaseHTTPRequestHandler):
    server_version = "PCPhoneRemote/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {self.client_address[0]} - {fmt % args}")

    @property
    def pin(self) -> str:
        return self.server.pin  # type: ignore[attr-defined]

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])

    def is_authenticated(self) -> bool:
        cookie_header = self.headers.get("Cookie", "")
        cookies = http.cookies.SimpleCookie()
        cookies.load(cookie_header)
        token_cookie = cookies.get(SESSION_COOKIE)
        if token_cookie is None:
            return False

        token = token_cookie.value
        with SESSIONS_LOCK:
            expires_at = SESSIONS.get(token)
            if not expires_at or expires_at < time.time():
                SESSIONS.pop(token, None)
                return False

            SESSIONS[token] = time.time() + 60 * 60 * 12
            return True

    def send_bytes(self, status: int, content: bytes, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.send_bytes(200, b"ok", "text/plain; charset=utf-8")
            return

        if parsed.path == "/pair":
            self.send_bytes(200, pair_page(self.pin, self.port))
            return

        if parsed.path != "/":
            self.send_error(404)
            return

        if self.is_authenticated():
            self.send_bytes(200, remote_page())
        else:
            self.send_bytes(200, login_page())

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)

        if parsed.path == "/login":
            form = parse_qs(body.decode("utf-8", errors="replace"))
            if form.get("pin", [""])[0] != self.pin:
                self.send_bytes(403, login_page("Wrong PIN."))
                return

            token = secrets.token_urlsafe(32)
            with SESSIONS_LOCK:
                SESSIONS[token] = time.time() + 60 * 60 * 12

            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200")
            self.end_headers()
            return

        if parsed.path == "/api/command":
            if not self.is_authenticated():
                self.send_bytes(401, json.dumps({"message": "Not authenticated"}).encode("utf-8"), "application/json")
                return

            try:
                payload = json.loads(body.decode("utf-8"))
                command = payload.get("command")
            except (json.JSONDecodeError, UnicodeDecodeError):
                command = None

            if command not in COMMANDS:
                self.send_bytes(400, json.dumps({"message": "Unknown command"}).encode("utf-8"), "application/json")
                return

            try:
                run_command(command)
            except Exception as exc:
                self.send_bytes(500, json.dumps({"message": f"Failed: {exc}"}).encode("utf-8"), "application/json")
                return

            label = COMMANDS[command]["label"]
            self.send_bytes(200, json.dumps({"message": f"{label} sent."}).encode("utf-8"), "application/json")
            return

        self.send_error(404)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--host", default=os.environ.get("REMOTE_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("REMOTE_PORT", "8765")))
    parser.add_argument("--pin", default=os.environ.get("REMOTE_PIN", DEFAULT_PIN))
    return parser.parse_args()


def main() -> int:
    if os.name != "nt":
        print("This app is intended for Windows commands.", file=sys.stderr)

    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), RemoteHandler)
    server.pin = args.pin  # type: ignore[attr-defined]

    print(f"{APP_NAME} is running.")
    if args.pin:
        print("PIN is configured.")
    else:
        print("WARNING: no PIN is configured. Set REMOTE_PIN before real use.")
    print("Open one of these addresses on your phone while connected to the same Wi-Fi:")
    for address in local_addresses(args.port):
        print(f"  {address}")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
