"""Cross-platform installer & setup wizard for PC Phone Remote Pro.

Supports:
- Graphical Tkinter wizard (default when launched via install.bat / double-click)
- Unattended CLI installation (`python installer.py --silent [--pin 123456] [--with-unlock] [--no-start]`)
"""

from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
CONFIG_PATH = ROOT / "config.json"
ASSETS_DIR = ROOT / "assets"
DEFAULT_PORT = 8765


def is_windows() -> bool:
    return os.name == "nt"


def is_admin() -> bool:
    if not is_windows():
        return hasattr(os, "geteuid") and os.geteuid() == 0
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def ensure_dependencies(log_cb=None) -> None:
    required = {
        "PIL": "Pillow",
        "qrcode": "qrcode[pil]",
        "pystray": "pystray",
        "psutil": "psutil",
    }
    missing = [pkg for mod, pkg in required.items() if importlib.util.find_spec(mod) is None]
    if not missing:
        if log_cb:
            log_cb("Python dependencies already installed.")
        return
    req_file = ROOT / "requirements.txt"
    if log_cb:
        log_cb(f"Installing dependencies: {', '.join(missing)}...")
    cmd = [sys.executable, "-m", "pip", "install", "--quiet"]
    if req_file.exists():
        cmd.extend(["-r", str(req_file)])
    else:
        cmd.extend(missing)
    subprocess.run(cmd, cwd=str(ROOT), check=True)
    if log_cb:
        log_cb("Python dependencies installed.")


def generate_assets(log_cb=None) -> dict[str, Path]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import brand_icon  # noqa: PLC0415

    paths = brand_icon.ensure_brand_assets(ASSETS_DIR)
    if log_cb:
        log_cb(f"Generated logo assets in {ASSETS_DIR.name}/.")
    return paths


def primary_mac_address() -> str:
    try:
        import psutil  # noqa: PLC0415

        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        for iface, stat in stats.items():
            low = iface.lower()
            if not stat.isup or any(v in low for v in ("loopback", "vethernet", "hyper-v", "wsl", "docker", "vmware", "virtualbox")):
                continue
            for item in addrs.get(iface, []):
                if getattr(item.family, "name", "") in ("AF_LINK", "AF_PACKET") and item.address:
                    cleaned = item.address.replace("-", ":").upper()
                    if len(cleaned.split(":")) == 6 and cleaned != "00:00:00:00:00:00":
                        return cleaned
    except Exception:
        pass
    import uuid

    node = uuid.getnode()
    return ":".join(f"{(node >> shift) & 0xFF:02X}" for shift in range(40, -1, -8))


def detect_lan_ip() -> str:
    try:
        import psutil  # noqa: PLC0415

        candidates: list[tuple[int, str]] = []
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        for iface, items in addrs.items():
            st = stats.get(iface)
            if st is not None and not st.isup:
                continue
            low = iface.lower()
            for item in items:
                if item.family == socket.AF_INET and item.address and not item.address.startswith("127.") and not item.address.startswith("169.254."):
                    score = 10
                    if any(v in low for v in ("wi-fi", "wifi", "wlan", "ethernet", "eth", "enp", "wlp")):
                        score += 30
                    if any(v in low for v in ("vethernet", "hyper-v", "wsl", "docker", "tailscale", "zerotier", "vmware", "virtualbox")):
                        score -= 40
                    if item.address.startswith("192.168."):
                        score += 15
                    elif item.address.startswith("10."):
                        score += 10
                    candidates.append((score, item.address))
        if candidates:
            candidates.sort(key=lambda pair: pair[0], reverse=True)
            return candidates[0][1]
    except Exception:
        pass

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text("utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "pin": "",
        "share_dir": "",
        "rdp": {"host": "", "port": 3389, "username": "", "gateway": ""},
    }


def save_config_with_pin(pin: str, log_cb=None) -> dict:
    cfg = load_config()
    clean = pin.strip() or str(cfg.get("pin", "")).strip()
    if not clean:
        clean = f"{secrets.randbelow(900000) + 100000}"

    cfg["pin"] = clean
    cfg.pop("allowed_pins", None)
    cfg["mac"] = primary_mac_address()

    share_dir = Path(str(cfg.get("share_dir") or (Path.home() / "Downloads" / "PCPhoneRemote")))
    share_dir.mkdir(parents=True, exist_ok=True)
    cfg["share_dir"] = str(share_dir)

    rdp = cfg.get("rdp")
    if not isinstance(rdp, dict):
        cfg["rdp"] = {"host": "", "port": 3389, "username": "", "gateway": ""}

    tmp = ROOT / "config.json.tmp"
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(CONFIG_PATH)
    if log_cb:
        log_cb(f"Saved config.json (unified PIN configured, MAC {cfg['mac']}).")
    return cfg


def configure_windows_firewall_and_unlock(install_unlock: bool, configure_fw: bool, log_cb=None) -> None:
    if not is_windows() or (not configure_fw and not install_unlock):
        return

    ps_lines = [
        "$ErrorActionPreference = 'Stop'",
    ]
    if configure_fw:
        ps_lines.extend([
            "netsh advfirewall firewall delete rule name=\"PC Phone Remote Server (TCP 8765)\" | Out-Null",
            "netsh advfirewall firewall add rule name=\"PC Phone Remote Server (TCP 8765)\" dir=in action=allow protocol=TCP localport=8765 profile=any | Out-Null",
            "netsh advfirewall firewall delete rule name=\"PC Phone Remote Discovery (UDP 8766)\" | Out-Null",
            "netsh advfirewall firewall add rule name=\"PC Phone Remote Discovery (UDP 8766)\" dir=in action=allow protocol=UDP localport=8766 profile=any | Out-Null",
        ])

    unlock_script = REPO_ROOT / "windows-unlock" / "install-unlock.ps1"
    if install_unlock and unlock_script.exists():
        escaped = str(unlock_script).replace("'", "''")
        ps_lines.append(f"Set-Location '{str(unlock_script.parent).replace(chr(39), chr(39)*2)}'")
        ps_lines.append(f"& '{escaped}'")

    if len(ps_lines) <= 1:
        return

    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as handle:
        handle.write("\n".join(ps_lines) + "\n")
        temp_ps1 = Path(handle.name)

    try:
        if is_admin():
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(temp_ps1)],
                check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            if log_cb:
                log_cb("Requesting Administrator permission for Firewall / Lock Screen module...")
            quoted_ps1 = str(temp_ps1).replace("'", "''")
            elevated = (
                "$p = Start-Process powershell -Verb RunAs -Wait -PassThru "
                f"-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','{quoted_ps1}'; "
                "exit $p.ExitCode"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", elevated],
                check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        if log_cb:
            steps = []
            if configure_fw:
                steps.append("Windows Firewall (TCP 8765, UDP 8766)")
            if install_unlock and unlock_script.exists():
                steps.append("Windows Lock Screen Provider")
            log_cb("Configured: " + ", ".join(steps) + ".")
    except subprocess.CalledProcessError as exc:
        if log_cb:
            log_cb(f"Warning: Elevation step skipped or failed (code {exc.returncode}).")
    finally:
        try:
            temp_ps1.unlink(missing_ok=True)
        except OSError:
            pass


def configure_autostart(log_cb=None) -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import autostart  # noqa: PLC0415

    autostart.enable()
    if log_cb:
        log_cb("User autostart configured.")


def create_windows_shortcuts(log_cb=None) -> None:
    if not is_windows():
        return
    ico = ASSETS_DIR / "app_icon.ico"
    pyw = Path(sys.executable).with_name("pythonw.exe")
    if not pyw.exists():
        pyw = Path(sys.executable)

    ps_script = f"""
$ws = New-Object -ComObject WScript.Shell
$desktop = $ws.SpecialFolders("Desktop")
$startMenu = Join-Path $env:APPDATA "Microsoft\\Windows\\Start Menu\\Programs\\PC Phone Remote"
New-Item -ItemType Directory -Force -Path $startMenu | Out-Null

function Make-Link($dir, $name, $target, $args, $desc) {{
    $lnk = $ws.CreateShortcut((Join-Path $dir "$name.lnk"))
    $lnk.TargetPath = $target
    $lnk.Arguments = $args
    $lnk.WorkingDirectory = "{str(ROOT).replace('"', '')}"
    $lnk.IconLocation = "{str(ico).replace('"', '')}"
    $lnk.Description = $desc
    $lnk.Save()
}}

Make-Link $desktop "PC Phone Remote" "wscript.exe" '"{str(ROOT / "start-hidden.vbs")}"' "Start PC Phone Remote background server"
Make-Link $startMenu "PC Phone Remote" "wscript.exe" '"{str(ROOT / "start-hidden.vbs")}"' "Start PC Phone Remote background server"
Make-Link $startMenu "Configure PC Phone Remote" "{str(pyw)}" '"{str(ROOT / "configure.py")}"' "Open PC Phone Remote configuration"
Make-Link $desktop "Configure PC Phone Remote" "{str(pyw)}" '"{str(ROOT / "configure.py")}"' "Open PC Phone Remote configuration"
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if log_cb:
        log_cb("Created Desktop and Start Menu shortcuts.")


def start_background_server(log_cb=None) -> None:
    try:
        import psutil  # noqa: PLC0415

        current_pid = os.getpid()
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if proc.info["pid"] == current_pid:
                    continue
                cmd = " ".join(proc.info.get("cmdline") or []).lower()
                if "pc-phone-remote" in cmd and "app.py" in cmd:
                    proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass

    if is_windows():
        vbs = ROOT / "start-hidden.vbs"
        if vbs.exists():
            subprocess.Popen(
                ["wscript.exe", str(vbs)],
                cwd=str(ROOT),
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if log_cb:
                log_cb("Started background server via start-hidden.vbs.")
            return

    py_exec = Path(sys.executable).with_name("pythonw.exe")
    if not is_windows() or not py_exec.exists():
        py_exec = Path(sys.executable)
    subprocess.Popen(
        [str(py_exec), str(ROOT / "app.py"), "--host", "0.0.0.0", "--port", str(DEFAULT_PORT)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=not is_windows(),
    )
    if log_cb:
        log_cb("Started background server (app.py).")


def build_connect_links(cfg: dict, port: int = DEFAULT_PORT) -> tuple[str, str]:
    ip = detect_lan_ip()
    host_name = socket.gethostname()
    pin = str(cfg.get("pin", "")).strip()
    android_uri = "pcphone://add?" + urlencode(
        {"name": host_name, "host": ip, "port": str(port), "pin": pin}
    )
    ios_url = f"http://{ip}:{port}/app"
    return android_uri, ios_url


def run_installation(
    pin: str,
    configure_fw: bool = True,
    install_unlock: bool = False,
    enable_autostart: bool = True,
    create_shortcuts: bool = True,
    start_server: bool = True,
    log_cb=None,
) -> dict:
    ensure_dependencies(log_cb)
    generate_assets(log_cb)
    cfg = save_config_with_pin(pin, log_cb)
    if is_windows():
        configure_windows_firewall_and_unlock(install_unlock, configure_fw, log_cb)
        if create_shortcuts:
            create_windows_shortcuts(log_cb)
    if enable_autostart:
        configure_autostart(log_cb)
    if start_server:
        start_background_server(log_cb)
    return cfg


def launch_gui() -> None:
    ensure_dependencies()
    generate_assets()
    cfg = load_config()
    initial_pin = str(cfg.get("pin", "")).strip() or f"{secrets.randbelow(900000) + 100000}"

    root = tk.Tk()
    root.title("PC Phone Remote Pro — Установщик / Installer")
    root.geometry("620x740")
    root.minsize(560, 680)
    root.configure(bg="#0B0B10")

    ico_path = ASSETS_DIR / "app_icon.ico"
    if ico_path.exists():
        try:
            root.iconbitmap(default=str(ico_path))
        except tk.TclError:
            pass

    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TFrame", background="#0B0B10")
    style.configure("Card.TFrame", background="#13141C")
    style.configure("TLabel", background="#0B0B10", foreground="#F2F2F7", font=("Segoe UI", 10))
    style.configure("Card.TLabel", background="#13141C", foreground="#F2F2F7", font=("Segoe UI", 10))
    style.configure("Muted.TLabel", background="#13141C", foreground="#9CA3AF", font=("Segoe UI", 9))
    style.configure("Title.TLabel", background="#0B0B10", foreground="#FFFFFF", font=("Segoe UI", 16, "bold"))
    style.configure("TCheckbutton", background="#13141C", foreground="#F2F2F7", font=("Segoe UI", 10))
    style.configure("Accent.TButton", background="#8B7CFF", foreground="#FFFFFF", font=("Segoe UI", 11, "bold"), padding=10)
    style.map("Accent.TButton", background=[("active", "#7363EB")])
    style.configure("Secondary.TButton", background="#232534", foreground="#F2F2F7", font=("Segoe UI", 9, "bold"), padding=7)

    container = ttk.Frame(root, padding=20)
    container.pack(fill="both", expand=True)

    header = ttk.Frame(container)
    header.pack(fill="x", pady=(0, 12))
    logo_photo = None
    png192 = ASSETS_DIR / "app_icon_192.png"
    if png192.exists():
        from PIL import Image, ImageTk  # noqa: PLC0415

        img = Image.open(png192).resize((54, 54), Image.Resampling.LANCZOS)
        logo_photo = ImageTk.PhotoImage(img)
        logo_lbl = tk.Label(header, image=logo_photo, bg="#0B0B10", bd=0)
        logo_lbl.image = logo_photo
        logo_lbl.pack(side="left", padx=(0, 12))

    title_col = ttk.Frame(header)
    title_col.pack(side="left", fill="x", expand=True)
    ttk.Label(title_col, text="PC Phone Remote Pro", style="Title.TLabel").pack(anchor="w")
    ttk.Label(
        title_col,
        text="Быстрая установка сервера, автозапуска, фаервола и подключения телефона",
        background="#0B0B10",
        foreground="#9CA3AF",
        font=("Segoe UI", 9),
    ).pack(anchor="w")

    # Card 1: Configuration options
    setup_frame = ttk.Frame(container, style="Card.TFrame", padding=18)
    setup_frame.pack(fill="both", expand=True)

    ttk.Label(
        setup_frame,
        text="1. Единый PIN-код подключения и входа",
        style="Card.TLabel",
        font=("Segoe UI", 11, "bold"),
    ).pack(anchor="w")
    ttk.Label(
        setup_frame,
        text="Этот же PIN-код используется при подключении с телефона (Android / iPhone) и для экрана входа.",
        style="Muted.TLabel",
        wraplength=540,
    ).pack(anchor="w", pady=(2, 8))

    pin_var = tk.StringVar(value=initial_pin)
    pin_entry = ttk.Entry(setup_frame, textvariable=pin_var, font=("Consolas", 14, "bold"))
    pin_entry.pack(fill="x", pady=(0, 14))

    fw_var = tk.BooleanVar(value=is_windows())
    auto_var = tk.BooleanVar(value=True)
    shortcut_var = tk.BooleanVar(value=is_windows())
    unlock_var = tk.BooleanVar(value=(REPO_ROOT / "windows-unlock" / "install-unlock.ps1").exists() and is_windows())

    ttk.Label(setup_frame, text="2. Компоненты установки", style="Card.TLabel", font=("Segoe UI", 11, "bold")).pack(
        anchor="w", pady=(0, 6)
    )
    if is_windows():
        ttk.Checkbutton(setup_frame, text="Открыть порты Windows Firewall (TCP 8765 и UDP 8766)", variable=fw_var).pack(
            anchor="w", pady=3
        )
        ttk.Checkbutton(setup_frame, text="Создать ярлыки на Рабочем столе и в меню «Пуск»", variable=shortcut_var).pack(
            anchor="w", pady=3
        )
        if (REPO_ROOT / "windows-unlock" / "install-unlock.ps1").exists():
            ttk.Checkbutton(
                setup_frame,
                text="Установить модуль разблокировки с экрана входа Windows (требует права админа)",
                variable=unlock_var,
            ).pack(anchor="w", pady=3)
    ttk.Checkbutton(setup_frame, text="Добавить в автозапуск при старте системы", variable=auto_var).pack(
        anchor="w", pady=3
    )

    log_box = tk.Text(
        setup_frame,
        height=7,
        bg="#0B0B10",
        fg="#D1D5DB",
        insertbackground="#FFFFFF",
        relief="flat",
        font=("Consolas", 9),
    )
    log_box.pack(fill="x", pady=(12, 12))
    log_box.insert("end", "Готово к установке. Нажмите кнопку ниже.\n")
    log_box.configure(state="disabled")

    def append_log(line: str) -> None:
        def _write() -> None:
            log_box.configure(state="normal")
            log_box.insert("end", f"• {line}\n")
            log_box.see("end")
            log_box.configure(state="disabled")

        root.after(0, _write)

    # Result screen frame (hidden until installation completes)
    done_frame = ttk.Frame(container, style="Card.TFrame", padding=18)
    qr_label = tk.Label(done_frame, bg="#FFFFFF", bd=6)
    qr_mode = tk.StringVar(value="android")
    qr_info_var = tk.StringVar(value="")
    link_var = tk.StringVar(value="")
    saved_cfg_ref: dict[str, dict] = {}

    def render_qr() -> None:
        import qrcode  # noqa: PLC0415
        from PIL import ImageTk  # noqa: PLC0415

        current_cfg = saved_cfg_ref.get("cfg") or cfg
        android_uri, ios_url = build_connect_links(current_cfg)
        target = android_uri if qr_mode.get() == "android" else ios_url
        qr_img = qrcode.make(target).convert("RGB").resize((220, 220))
        photo = ImageTk.PhotoImage(qr_img)
        qr_label.configure(image=photo)
        qr_label.image = photo
        link_var.set(target)
        if qr_mode.get() == "android":
            qr_info_var.set(f"Android: нажмите «Автопоиск ПК в Wi-Fi» или вставьте код. Единый PIN: {current_cfg.get('pin', '')}")
        else:
            qr_info_var.set(f"iPhone / iPad Safari: откройте {ios_url} и нажмите «Поделиться → На экран Домой».")

    def show_done_screen(final_cfg: dict) -> None:
        saved_cfg_ref["cfg"] = final_cfg
        setup_frame.pack_forget()
        done_frame.pack(fill="both", expand=True)

        ttk.Label(
            done_frame,
            text="✓ Установка завершена и сервер запущен!",
            style="Card.TLabel",
            foreground="#3DD68C",
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")

        mode_row = ttk.Frame(done_frame, style="Card.TFrame")
        mode_row.pack(fill="x", pady=(10, 8))
        ttk.Button(
            mode_row,
            text="🤖 QR для Android",
            style="Secondary.TButton",
            command=lambda: (qr_mode.set("android"), render_qr()),
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            mode_row,
            text="🍎 QR для iPhone / iPad (PWA)",
            style="Secondary.TButton",
            command=lambda: (qr_mode.set("ios"), render_qr()),
        ).pack(side="left")

        qr_label.pack(pady=8)
        ttk.Label(done_frame, textvariable=qr_info_var, style="Muted.TLabel", wraplength=540).pack(anchor="w", pady=(0, 6))
        link_entry = ttk.Entry(done_frame, textvariable=link_var, font=("Consolas", 9))
        link_entry.pack(fill="x", pady=(0, 10))

        action_row = ttk.Frame(done_frame, style="Card.TFrame")
        action_row.pack(fill="x")

        def copy_current_link() -> None:
            root.clipboard_clear()
            root.clipboard_append(link_var.get())
            messagebox.showinfo("Скопировано", "Ссылка/код скопированы в буфер обмена.")

        ttk.Button(action_row, text="Копировать ссылку", style="Secondary.TButton", command=copy_current_link).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(
            action_row,
            text="Настроить вход Windows (QR отпечатка)",
            style="Secondary.TButton",
            command=lambda: subprocess.Popen([sys.executable, str(ROOT / "configure.py")], cwd=str(ROOT)),
        ).pack(side="left", padx=(0, 8))
        ttk.Button(action_row, text="Готово", style="Accent.TButton", command=root.destroy).pack(side="right")

        render_qr()

    install_btn = ttk.Button(setup_frame, text="Установить и запустить", style="Accent.TButton")

    def on_install() -> None:
        pin = pin_var.get().strip()
        if len(pin) < 4:
            messagebox.showwarning("PIN-код", "Введите PIN-код длиной минимум 4 символа.")
            return
        install_btn.configure(state="disabled")

        def worker() -> None:
            try:
                final_cfg = run_installation(
                    pin=pin,
                    configure_fw=fw_var.get(),
                    install_unlock=unlock_var.get(),
                    enable_autostart=auto_var.get(),
                    create_shortcuts=shortcut_var.get(),
                    start_server=True,
                    log_cb=append_log,
                )
                root.after(0, lambda: show_done_screen(final_cfg))
            except Exception as exc:  # noqa: BLE001
                append_log(f"ERROR: {exc}")
                root.after(0, lambda: (install_btn.configure(state="normal"), messagebox.showerror("Ошибка", str(exc))))

        threading.Thread(target=worker, daemon=True).start()

    install_btn.configure(command=on_install)
    install_btn.pack(fill="x")

    root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Installer for PC Phone Remote Pro")
    parser.add_argument("--silent", action="store_true", help="Run unattended installation without GUI")
    parser.add_argument("--pin", default="", help="Unified PIN code to configure")
    parser.add_argument("--with-unlock", action="store_true", help="Install Windows lock screen credential provider")
    parser.add_argument("--no-firewall", action="store_true", help="Skip Windows Firewall rule creation")
    parser.add_argument("--no-autostart", action="store_true", help="Skip enabling OS autostart")
    parser.add_argument("--no-shortcuts", action="store_true", help="Skip Desktop & Start Menu shortcuts")
    parser.add_argument("--no-start", action="store_true", help="Do not launch background server after install")
    args = parser.parse_args()

    if args.silent:
        cfg = run_installation(
            pin=args.pin,
            configure_fw=not args.no_firewall,
            install_unlock=args.with_unlock,
            enable_autostart=not args.no_autostart,
            create_shortcuts=not args.no_shortcuts,
            start_server=not args.no_start,
            log_cb=lambda msg: print(f"[installer] {msg}"),
        )
        android_uri, ios_url = build_connect_links(cfg)
        print(f"[installer] PC IP & Port : {detect_lan_ip()}:{DEFAULT_PORT}")
        print(f"[installer] Unified PIN  : {cfg.get('pin', '')}")
        print(f"[installer] iOS/Mobile   : {ios_url}")
        print(f"[installer] Android URI  : {android_uri}")
        return 0

    launch_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
