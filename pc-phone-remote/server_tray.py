from __future__ import annotations

import io
import json
import os
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import pystray
from PIL import Image, ImageDraw
from companion import Companion, load_config
from pro_features import check_github_updates, set_clipboard_text

APP_DIR = Path(__file__).resolve().parent
APP_FILE = APP_DIR / "app.py"
PORT = int(os.environ.get("REMOTE_PORT", "8765"))

server_process: subprocess.Popen | None = None
_stop_event = threading.Event()


def pythonw_path() -> str:
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate if candidate.exists() else exe)


def _server_scheme() -> str:
    try:
        cfg = load_config(APP_DIR / "config.json")
        if cfg.get("https_enabled"):
            return "https"
    except Exception:
        pass
    return "http"


def _local_url(path: str = "/desktop") -> str:
    return f"{_server_scheme()}://127.0.0.1:{PORT}{path}"


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


def open_desktop_control_center() -> None:
    exe = APP_DIR / "PCPhoneRemote.exe"
    if os.name == "nt" and exe.exists():
        subprocess.Popen([str(exe)], cwd=str(APP_DIR), creationflags=subprocess.CREATE_NO_WINDOW)
        return
    try:
        from configure import open_animated_desktop_app
        if open_animated_desktop_app(PORT):
            return
    except Exception:
        pass
    webbrowser.open(_local_url("/desktop"))


def open_pairing() -> None:
    webbrowser.open(_local_url("/pair"))


def open_shared_folder() -> None:
    target = str(Companion(load_config()).root)
    if os.name == "nt":
        os.startfile(target)
    else:
        subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def show_quick_qr_popup() -> None:
    """Open a lightweight standalone Tkinter QR popup without launching a browser."""
    def _popup() -> None:
        import tkinter as tk
        from PIL import ImageTk
        from app import preferred_host, qr_png_bytes, setup_uri

        cfg = load_config(APP_DIR / "config.json")
        pin = str(cfg.get("pin") or "")
        host_url = preferred_host(PORT)
        uri = setup_uri(pin, PORT)
        png = qr_png_bytes(uri)

        root = tk.Tk()
        root.title("PC Phone Remote — Быстрый QR")
        root.configure(bg="#0D0E16")
        root.resizable(False, False)

        tk.Label(
            root,
            text="Сканируйте QR в приложении на телефоне",
            fg="#F4F6FC",
            bg="#0D0E16",
            font=("Segoe UI", 11, "bold"),
            padx=18,
            pady=10,
        ).pack()

        if png:
            pil_img = Image.open(io.BytesIO(png)).resize((230, 230))
            tk_img = ImageTk.PhotoImage(pil_img)
            lbl = tk.Label(root, image=tk_img, bg="#FFFFFF", bd=6)
            lbl.image = tk_img
            lbl.pack(padx=20, pady=6)

        tk.Label(
            root,
            text=f"{host_url}\nPIN: {pin or '—'}",
            fg="#5EEAD4",
            bg="#0D0E16",
            font=("Consolas", 11, "bold"),
            pady=8,
        ).pack()

        tk.Button(
            root,
            text="Открыть Центр управления",
            command=lambda: (root.destroy(), open_desktop_control_center()),
            bg="#FF4D8D",
            fg="#FFFFFF",
            relief="flat",
            padx=14,
            pady=6,
        ).pack(pady=(0, 14))
        root.mainloop()

    threading.Thread(target=_popup, daemon=True).start()


def copy_pin_to_clipboard(icon: pystray.Icon) -> None:
    try:
        cfg = load_config(APP_DIR / "config.json")
        pin = str(cfg.get("pin") or "")
        if not pin:
            icon.notify("PIN ещё не задан", "PC Phone Remote")
            return
        set_clipboard_text(pin)
        icon.notify(f"PIN скопирован в буфер обмена: {pin}", "PC Phone Remote")
    except Exception as exc:
        icon.notify(f"Не удалось скопировать PIN: {exc}", "PC Phone Remote")


def check_updates_async(icon: pystray.Icon) -> None:
    def _worker() -> None:
        res = check_github_updates()
        if not res.get("ok"):
            icon.notify(f"Ошибка проверки обновлений: {res.get('error', '')[:80]}", "PC Phone Remote")
            return
        if res.get("update_available"):
            latest = res.get("latest_version")
            icon.notify(f"Доступна новая версия v{latest}! Открываю страницу загрузки…", "PC Phone Remote")
            webbrowser.open(str(res.get("release_url") or ""))
        else:
            icon.notify(f"Установлена актуальная версия v{res.get('current_version')}", "PC Phone Remote")

    threading.Thread(target=_worker, daemon=True).start()


def _client_connection_watcher(icon: pystray.Icon) -> None:
    """Poll local admin endpoint and show a tray toast when a new phone connects."""
    last_ts = 0.0
    last_ip = ""
    ctx = ssl._create_unverified_context()
    while not _stop_event.wait(5.0):
        try:
            url = _local_url("/api/local/admin")
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=2.5, context=ctx if url.startswith("https://") else None) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            lc = data.get("last_client_seen") or {}
            ts = float(lc.get("ts") or 0.0)
            ip = str(lc.get("ip") or "")
            ago = float(lc.get("ago_sec") or 999.0)
            if ip and ago < 10.0 and ts > last_ts and (ip != last_ip or (ts - last_ts) > 45.0):
                last_ts = ts
                last_ip = ip
                icon.notify(f"Подключён клиент: {ip} ({lc.get('path') or '/'})", "PC Phone Remote")
        except Exception:
            pass


def create_icon(status_color: str = "online") -> Image.Image:
    try:
        from brand_icon import create_brand_image
        return create_brand_image(64, status_color=status_color)
    except Exception:
        image = Image.new("RGBA", (64, 64), (13, 14, 24, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((10, 12, 54, 48), radius=8, fill=(139, 124, 255, 255))
        draw.rectangle((25, 50, 39, 54), fill=(56, 189, 248, 255))
        draw.ellipse((43, 8, 56, 21), fill=(61, 214, 140, 255))
        return image


def quit_app(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    _stop_event.set()
    stop_server()
    icon.stop()


def main() -> None:
    start_server()
    icon = pystray.Icon(
        "PC Phone Remote",
        create_icon(),
        "PC Phone Remote",
        menu=pystray.Menu(
            pystray.MenuItem("Открыть Центр управления", lambda icon, item: open_desktop_control_center(), default=True),
            pystray.MenuItem("Быстрый QR-код", lambda icon, item: show_quick_qr_popup()),
            pystray.MenuItem("Скопировать PIN", lambda icon, item: copy_pin_to_clipboard(icon)),
            pystray.MenuItem("Страница /pair", lambda icon, item: open_pairing()),
            pystray.MenuItem("Открыть папку обмена", lambda icon, item: open_shared_folder()),
            pystray.MenuItem("Проверить обновления", lambda icon, item: check_updates_async(icon)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Перезапустить сервер", lambda icon, item: (stop_server(), start_server())),
            pystray.MenuItem("Остановить сервер", lambda icon, item: stop_server()),
            pystray.MenuItem("Выход", quit_app),
        ),
    )
    threading.Thread(target=_client_connection_watcher, args=(icon,), daemon=True).start()
    icon.run()


if __name__ == "__main__":
    main()
