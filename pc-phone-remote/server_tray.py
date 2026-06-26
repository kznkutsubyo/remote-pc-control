from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

import pystray
from PIL import Image, ImageDraw


APP_DIR = Path(__file__).resolve().parent
APP_FILE = APP_DIR / "app.py"
PORT = int(os.environ.get("REMOTE_PORT", "8765"))

server_process: subprocess.Popen | None = None


def pythonw_path() -> str:
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate if candidate.exists() else exe)


def start_server() -> None:
    global server_process
    if server_process and server_process.poll() is None:
        return

    server_process = subprocess.Popen(
        [pythonw_path(), str(APP_FILE)],
        cwd=str(APP_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def stop_server() -> None:
    global server_process
    if server_process and server_process.poll() is None:
        server_process.terminate()
        try:
            server_process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            server_process.kill()
    server_process = None


def open_remote() -> None:
    webbrowser.open(f"http://127.0.0.1:{PORT}/")


def open_pairing() -> None:
    webbrowser.open(f"http://127.0.0.1:{PORT}/pair")


def create_icon() -> Image.Image:
    image = Image.new("RGBA", (64, 64), (18, 18, 30, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((10, 12, 54, 48), radius=8, fill=(161, 105, 255, 255))
    draw.rectangle((25, 50, 39, 54), fill=(161, 105, 255, 255))
    draw.rectangle((19, 55, 45, 58), fill=(161, 105, 255, 255))
    draw.ellipse((43, 8, 56, 21), fill=(75, 224, 163, 255))
    return image


def quit_app(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    stop_server()
    icon.stop()


def main() -> None:
    start_server()
    icon = pystray.Icon(
        "PC Phone Remote",
        create_icon(),
        "PC Phone Remote",
        menu=pystray.Menu(
            pystray.MenuItem("Open remote", lambda icon, item: open_remote()),
            pystray.MenuItem("Pair phone", lambda icon, item: open_pairing()),
            pystray.MenuItem("Restart server", lambda icon, item: (stop_server(), start_server())),
            pystray.MenuItem("Stop server", lambda icon, item: stop_server()),
            pystray.MenuItem("Quit", quit_app),
        ),
    )
    icon.run()


if __name__ == "__main__":
    main()
