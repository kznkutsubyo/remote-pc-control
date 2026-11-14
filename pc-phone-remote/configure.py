"""Local desktop setup, unified PIN, QR code pairing & Phone Sign-In enrollment wizard."""
from __future__ import annotations

import base64
import ctypes
import getpass
import hashlib
import hmac
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import tkinter as tk
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import urlencode, urlparse

from app import preferred_host, setup_uri
from autostart import disable as autostart_disable, enable as autostart_enable, is_enabled as autostart_is_enabled
from companion import load_config, primary_mac_address
from unlock_ipc import pipe_transact

ROOT = Path(__file__).resolve().parent


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    cleaned = text.strip()
    pad = "=" * ((4 - len(cleaned) % 4) % 4)
    return base64.urlsafe_b64decode(cleaned + pad)


def _open_folder_native(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(path))
    else:
        subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _is_server_online(port: int = 8765) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.8) as resp:
            return resp.status == 200
    except Exception:
        return False


def _start_server_detached() -> None:
    if os.name == "nt":
        vbs = ROOT / "start-hidden.vbs"
        if vbs.exists():
            subprocess.Popen(["wscript.exe", str(vbs)], cwd=str(ROOT), creationflags=subprocess.CREATE_NO_WINDOW)
            return
    py = sys.executable or "python3"
    subprocess.Popen(
        [py, str(ROOT / "app.py")],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def build_enroll_uri(config: dict, port: int, enroll_resp: dict, phone_pin: str = "", host_override: str = "") -> str:
    base = preferred_host(port)
    parsed = urlparse(base)
    clean_host = host_override.strip()
    if clean_host.startswith("http://") or clean_host.startswith("https://"):
        host_val = clean_host
        port_val = str(port)
    elif clean_host and ":" in clean_host:
        h_part, p_part = clean_host.rsplit(":", 1)
        host_val = h_part.strip()
        port_val = p_part.strip() or str(port)
    elif clean_host:
        host_val = clean_host
        port_val = str(parsed.port or port)
    else:
        host_val = parsed.hostname or "127.0.0.1"
        port_val = str(parsed.port or port)

    query: dict[str, str] = {
        "name": socket.gethostname() or "My PC",
        "host": host_val,
        "port": port_val,
        "pin": str(config.get("pin", "")),
        "token": str(enroll_resp.get("enroll_token", "")),
        "fp": str(enroll_resp.get("pc_pub_fp", "")),
        "sid": str(enroll_resp.get("user_sid", "")),
        "user": str(enroll_resp.get("qualified_user", "")),
        "mode": str(enroll_resp.get("vault_mode", "split_key")),
    }
    split_key_b64 = str(enroll_resp.get("split_key", "")).strip()
    clean_phone_pin = phone_pin.strip()
    if split_key_b64:
        if clean_phone_pin:
            raw_k = _b64url_decode(split_key_b64)
            salt = secrets.token_bytes(16)
            mask = hashlib.pbkdf2_hmac("sha256", clean_phone_pin.encode("utf-8"), salt, 100_000, dklen=32)
            masked_k = bytes(a ^ b for a, b in zip(raw_k, mask))
            tag = hmac.new(mask, b"pcpr-pin-check-v1", hashlib.sha256).digest()[:16]
            query["mode"] = "pin_split_key"
            query["pk"] = _b64url_encode(masked_k)
            query["ps"] = _b64url_encode(salt)
            query["pt"] = _b64url_encode(tag)
        else:
            query["k"] = split_key_b64
    return "pcphone://enroll?" + urlencode(query)


def open_animated_desktop_app(port: int = 8765) -> bool:
    """Ensure background server is running and open the animated Desktop Control Center."""
    if not _is_server_online(port):
        _start_server_detached()
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if _is_server_online(port):
                break
            time.sleep(0.2)

    url = f"http://127.0.0.1:{port}/desktop"
    browser_args = [f"--app={url}", "--window-size=1140,830", "--new-window"]
    candidates: list[str] = []
    if os.name == "nt":
        for env_key in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData"):
            base = os.environ.get(env_key, "")
            if not base:
                continue
            candidates.extend([
                os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(base, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            ])
    else:
        for cmd_name in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge", "brave-browser"):
            found = shutil.which(cmd_name)
            if found:
                candidates.append(found)

    for exe in candidates:
        if exe and os.path.exists(exe):
            try:
                subprocess.Popen(
                    [exe, *browser_args],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                return True
            except OSError:
                continue

    return bool(webbrowser.open(url))


def main() -> None:
    if "--legacy-tk" not in sys.argv:
        if open_animated_desktop_app(8765):
            return

    config = load_config()
    window = tk.Tk()
    window.title("PC Phone Remote Pro — Быстрая настройка ПК")
    window.geometry("780x860")
    window.minsize(680, 760)
    window.configure(bg="#0B0B10")

    try:
        from brand_icon import ensure_brand_assets
        assets = ensure_brand_assets()
        if os.name == "nt" and assets["ico"].exists():
            window.iconbitmap(str(assets["ico"]))
        elif assets["png_192"].exists():
            icon_photo = tk.PhotoImage(file=str(assets["png_192"]))
            window.iconphoto(True, icon_photo)
    except Exception:
        pass

    style = ttk.Style(window)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(".", background="#0B0B10", foreground="#F2F2F5", font=("Segoe UI", 10))
    style.configure("Card.TFrame", background="#15151C")
    style.configure("Banner.TFrame", background="#1E1E2A")
    style.configure("Card.TLabel", background="#15151C", foreground="#F2F2F5")
    style.configure("Banner.TLabel", background="#1E1E2A", foreground="#F5B14C")
    style.configure("Muted.TLabel", background="#15151C", foreground="#9A9AA8")
    style.configure("Card.TCheckbutton", background="#15151C", foreground="#D8D8E4")
    style.map("Card.TCheckbutton", background=[("active", "#15151C")])
    style.configure("Accent.TButton", background="#8B7CFF", foreground="#0B0B10", font=("Segoe UI", 10, "bold"), padding=8)
    style.map("Accent.TButton", background=[("active", "#9F92FF")])
    style.configure("Secondary.TButton", background="#22222E", foreground="#F2F2F5", padding=8)
    style.configure("TNotebook", background="#0B0B10", borderwidth=0)
    style.configure("TNotebook.Tab", background="#15151C", foreground="#8C8C99", padding=(14, 8))
    style.map("TNotebook.Tab", background=[("selected", "#8B7CFF")], foreground=[("selected", "#0B0B10")])

    outer = ttk.Frame(window, padding=18)
    outer.pack(fill="both", expand=True)

    # Header + Readiness Checklist Strip
    ttk.Label(outer, text="PC Phone Remote Pro", font=("Segoe UI", 21, "bold")).pack(anchor="w")
    ttk.Label(
        outer,
        text="Упрощённая настройка: единый PIN-код, QR-подключение и вход с Android / iPhone",
        foreground="#8C8C99",
    ).pack(anchor="w", pady=(2, 10))

    ready_frame = ttk.Frame(outer, style="Card.TFrame", padding=12)
    ready_frame.pack(fill="x", pady=(0, 12))

    srv_dot_var = tk.StringVar(value="● Проверка сервера...")
    auto_dot_var = tk.StringVar(value="● Проверка автозапуска...")
    pair_dot_var = tk.StringVar(value="● Проверка входа...")

    srv_lbl = ttk.Label(ready_frame, textvariable=srv_dot_var, style="Card.TLabel", font=("Segoe UI", 9, "bold"))
    srv_lbl.grid(row=0, column=0, sticky="w", padx=(0, 14))
    auto_lbl = ttk.Label(ready_frame, textvariable=auto_dot_var, style="Card.TLabel", font=("Segoe UI", 9, "bold"))
    auto_lbl.grid(row=0, column=1, sticky="w", padx=(0, 14))
    pair_lbl = ttk.Label(ready_frame, textvariable=pair_dot_var, style="Card.TLabel", font=("Segoe UI", 9, "bold"))
    pair_lbl.grid(row=0, column=2, sticky="w")

    start_srv_btn = ttk.Button(
        ready_frame,
        text="▶ Запустить сервер",
        style="Accent.TButton",
        command=lambda: (_start_server_detached(), window.after(1200, refresh_readiness)),
    )
    start_srv_btn.grid(row=0, column=3, sticky="e", padx=(10, 0))
    ready_frame.columnconfigure(2, weight=1)

    def show_qr_modal(uri: str, title: str = "QR-код подключения", hint: str = "") -> None:
        if not uri:
            messagebox.showwarning(title, "Сначала создайте код подключения или привязки.")
            return
        pop = tk.Toplevel(window)
        pop.title(title)
        pop.configure(bg="#15151C")
        pop.geometry("420x510")
        pop.transient(window)
        frame = ttk.Frame(pop, style="Card.TFrame", padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=title, style="Card.TLabel", font=("Segoe UI", 13, "bold")).pack(anchor="center", pady=(0, 6))
        if hint:
            ttk.Label(frame, text=hint, style="Muted.TLabel", wraplength=360, justify="center").pack(anchor="center", pady=(0, 10))
        try:
            import qrcode
            from PIL import ImageTk

            qr = qrcode.QRCode(box_size=8, border=2)
            qr.add_data(uri)
            qr.make(fit=True)
            img = qr.make_image(fill_color="#0B0B10", back_color="#FFFFFF").convert("RGB").resize((260, 260))
            photo = ImageTk.PhotoImage(img)
            img_lbl = tk.Label(frame, image=photo, bg="#FFFFFF", bd=6, relief="flat")
            img_lbl.image = photo  # type: ignore[attr-defined]
            img_lbl.pack(pady=8)
        except Exception:
            ttk.Label(frame, text="(QR-превью недоступно, используйте код ниже)", style="Muted.TLabel").pack(pady=10)

        code_box = ttk.Entry(frame, width=48)
        code_box.insert(0, uri)
        code_box.configure(state="readonly")
        code_box.pack(fill="x", pady=(8, 10))

        def _copy() -> None:
            window.clipboard_clear()
            window.clipboard_append(uri)
            messagebox.showinfo("Скопировано", "Код скопирован в буфер обмена.")

        ttk.Button(frame, text="Скопировать код", style="Accent.TButton", command=_copy).pack(fill="x", pady=(0, 6))
        ttk.Button(frame, text="Закрыть", style="Secondary.TButton", command=pop.destroy).pack(fill="x")

    def persist_unified_pin(new_pin: str) -> None:
        clean = new_pin.strip()
        if not clean:
            return
        latest = load_config()
        latest["pin"] = clean
        latest.pop("allowed_pins", None)
        latest["mac"] = primary_mac_address()
        temp = ROOT / "config.json.tmp"
        temp.write_text(json.dumps(latest, ensure_ascii=False, indent=2), "utf-8")
        temp.replace(ROOT / "config.json")
        config.update(latest)
        try:
            pin_entry.delete(0, "end")
            pin_entry.insert(0, clean)
        except Exception:
            pass

    notebook = ttk.Notebook(outer)
    notebook.pack(fill="both", expand=True)

    # ===================================================== TAB 1: Быстрый старт / Вход с телефона
    unlock_tab = ttk.Frame(notebook, style="Card.TFrame", padding=18)
    notebook.add(unlock_tab, text="  Быстрая привязка и вход  ")

    default_domain = os.environ.get("USERDOMAIN", socket.gethostname())
    default_user = getpass.getuser()

    is_win = os.name == "nt"
    if is_win:
        acct_info = pipe_transact({"op": "account.detect", "username": default_user}, timeout_ms=3000, auto_start=True)
    else:
        acct_info = {"is_msa": False}
    is_msa = bool(acct_info.get("is_msa"))
    msa_provider = str(acct_info.get("msa_provider") or "MicrosoftAccount")
    msa_principal = str(acct_info.get("msa_principal") or "")

    ttk.Label(
        unlock_tab,
        text="Единый PIN и привязка телефона (Android / iPhone)",
        style="Card.TLabel",
        font=("Segoe UI", 11, "bold"),
    ).pack(anchor="w")

    banner = ttk.Frame(unlock_tab, style="Banner.TFrame", padding=10)
    banner.pack(fill="x", pady=(8, 10))
    if not is_win:
        banner_text = (
            "🐧 Обнаружена система Linux.\n"
            "• На телефоне нажмите «Найти ПК в Wi-Fi», введите единый PIN сервера ниже — и сразу заработают тачпад, медиа, Stream Deck, файлы и разблокировка logind.\n"
            f"• Ссылка для iPhone / Safari: {preferred_host(8765)}/app"
        )
    elif is_msa and msa_principal:
        banner_text = (
            f"⚡ Аккаунт Microsoft: {msa_principal} (профиль «{default_user}»).\n"
            "• Пароль аккаунта: введите ПАРОЛЬ от этой почты Microsoft (короткий PIN экрана Windows хранится в TPM).\n"
            "• Единый PIN-код ниже будет автоматически использоваться и для подключения телефона, и для разблокировки Windows!"
        )
    else:
        banner_text = (
            "• Пароль аккаунта: введите пароль от вашей учётной записи Windows (не PIN Windows Hello).\n"
            "• Единый PIN-код ниже сохраняется сразу и как PIN сервера, и как PIN разблокировки с телефона!"
        )
    ttk.Label(banner, text=banner_text, style="Banner.TLabel", wraplength=690, justify="left").pack(anchor="w")

    status_var = tk.StringVar(value="Проверка статуса службы входа…")
    status_lbl = ttk.Label(unlock_tab, textvariable=status_var, style="Card.TLabel", foreground="#3DD68C", wraplength=690)
    status_lbl.pack(anchor="w", pady=(0, 8))

    form_grid = ttk.Frame(unlock_tab, style="Card.TFrame")
    form_grid.pack(fill="x", pady=2)

    ttk.Label(form_grid, text="Домен / Система:", style="Card.TLabel").grid(row=0, column=0, sticky="w", pady=4)
    domain_entry = ttk.Entry(form_grid, width=32)
    domain_entry.insert(0, (msa_provider if (is_msa and msa_principal) else default_domain) if is_win else "Linux")
    domain_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=4)

    ttk.Label(form_grid, text="Аккаунт / Пользователь:", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=4)
    user_entry = ttk.Entry(form_grid, width=32)
    user_entry.insert(0, msa_principal if (is_msa and msa_principal) else default_user)
    user_entry.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=4)

    pw_label_text = "Пароль от аккаунта:" if is_win else "Пароль (опционально):"
    ttk.Label(form_grid, text=pw_label_text, style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=4)
    pw_row = ttk.Frame(form_grid, style="Card.TFrame")
    pw_row.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=4)
    pw_entry = ttk.Entry(pw_row, show="•")
    pw_entry.pack(side="left", fill="x", expand=True)
    show_pw_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        pw_row,
        text="Показать",
        variable=show_pw_var,
        style="Card.TCheckbutton",
        command=lambda: pw_entry.configure(show="" if show_pw_var.get() else "•"),
    ).pack(side="left", padx=(8, 0))

    ttk.Label(form_grid, text="Единый PIN для телефона и ПК:", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=4)
    phone_pin_entry = ttk.Entry(form_grid, width=32, font=("Segoe UI", 10, "bold"))
    phone_pin_entry.insert(0, str(config.get("pin", "")))
    phone_pin_entry.grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=4)

    ttk.Label(
        form_grid,
        text="Один PIN на всё (например, 4–6 цифр). Он автоматически обновит сервер и привязку телефона.",
        style="Muted.TLabel",
        wraplength=460,
    ).grid(row=4, column=1, sticky="w", padx=(10, 0), pady=(0, 4))

    default_server_host = str(config.get("relay", {}).get("url") or "").strip()
    if not default_server_host:
        default_server_host = urlparse(preferred_host(8765)).hostname or "127.0.0.1"

    ttk.Label(form_grid, text="IP этого ПК / Relay URL:", style="Card.TLabel").grid(row=5, column=0, sticky="w", pady=4)
    server_host_entry = ttk.Entry(form_grid, width=32)
    server_host_entry.insert(0, default_server_host)
    server_host_entry.grid(row=5, column=1, sticky="ew", padx=(10, 0), pady=4)

    skip_verify_var = tk.BooleanVar(value=False)
    if is_win:
        ttk.Checkbutton(
            unlock_tab,
            text="Сохранить без локальной проверки кэша Windows (если раньше входили ТОЛЬКО по Windows PIN)",
            variable=skip_verify_var,
            style="Card.TCheckbutton",
        ).pack(anchor="w", pady=(6, 4))

    form_grid.columnconfigure(1, weight=1)

    enroll_code_var = tk.StringVar(value="")

    def refresh_unlock_status() -> None:
        if not is_win:
            status_var.set("✓ Linux готов: используйте единый PIN в приложении или откройте /app на iPhone.")
            status_lbl.configure(foreground="#3DD68C")
            pair_dot_var.set("● Linux logind готов ✓")
            pair_lbl.configure(foreground="#3DD68C")
            return
        resp = pipe_transact({"op": "unlock.status"}, timeout_ms=2500, auto_start=True)
        if not resp.get("ok"):
            status_var.set("Служба входа не отвечает: " + str(resp.get("message", "")))
            status_lbl.configure(foreground="#FF7A85")
            pair_dot_var.set("● Служба входа: требует внимания")
            pair_lbl.configure(foreground="#FF7A85")
            return
        prov_ok = bool(resp.get("provider_installed"))
        prov_note = (
            " | Модуль LogonUI: установлен ✓"
            if prov_ok
            else " | ⚠ Модуль экрана блокировки не установлен (кнопка ниже)"
        )
        if resp.get("enrolled"):
            status_var.set(f"✓ Телефон привязан: {resp.get('device_name')} · {resp.get('qualified_user')}{prov_note}")
            status_lbl.configure(foreground="#3DD68C" if prov_ok else "#F5B14C")
            pair_dot_var.set("● Вход привязан ✓" if prov_ok else "● Нужен LogonUI")
            pair_lbl.configure(foreground="#3DD68C" if prov_ok else "#F5B14C")
        else:
            status_var.set("Телефон ещё не привязан для входа в Windows. Заполните форму ниже." + prov_note)
            status_lbl.configure(foreground="#F5B14C")
            pair_dot_var.set("● Вход не привязан")
            pair_lbl.configure(foreground="#F5B14C")

    def refresh_readiness() -> None:
        srv_up = _is_server_online(8765)
        srv_dot_var.set("● Сервер: работает ✓" if srv_up else "● Сервер: остановлен")
        srv_lbl.configure(foreground="#3DD68C" if srv_up else "#FF7A85")
        if srv_up:
            start_srv_btn.state(["disabled"])
        else:
            start_srv_btn.state(["!disabled"])

        auto_on = autostart_is_enabled()
        auto_dot_var.set("● Автозапуск: вкл ✓" if auto_on else "● Автозапуск: выкл")
        auto_lbl.configure(foreground="#3DD68C" if auto_on else "#F5B14C")

    def install_lockscreen_provider() -> None:
        install_ps1 = ROOT.parent / "windows-unlock" / "install-unlock.ps1"
        if not install_ps1.exists():
            messagebox.showerror("Модуль экрана блокировки", f"Не найден скрипт установки:\n{install_ps1}")
            return
        params = f'-NoProfile -ExecutionPolicy Bypass -File "{install_ps1}"'
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", params, str(install_ps1.parent), 1)
        if rc <= 32:
            messagebox.showwarning(
                "Установка отменена",
                "Не удалось запустить установщик от имени Администратора. Подтвердите окно UAC для регистрации модуля.",
            )
            return
        window.after(3500, refresh_unlock_status)
        messagebox.showinfo(
            "Установка модуля экрана блокировки",
            "Запущена установка системного модуля PhoneUnlockProvider.dll и службы PhoneUnlockService.",
        )

    def start_enrollment() -> None:
        phone_pin = phone_pin_entry.get().strip()
        if phone_pin and len(phone_pin) < 4:
            messagebox.showwarning("Единый PIN-код", "PIN-код должен содержать минимум 4 символа (или оставьте пустым для биометрии).")
            return
        if phone_pin:
            persist_unified_pin(phone_pin)

        if not is_win:
            uri = setup_uri(phone_pin or str(config.get("pin", "")), 8765, socket.gethostname() or "Linux PC")
            enroll_code_var.set(uri)
            window.clipboard_clear()
            window.clipboard_append(uri)
            show_qr_modal(uri, "QR-код для Android / iPhone", f"Единый PIN: {config.get('pin', '')}\nДля iPhone Safari откройте: {preferred_host(8765)}/app")
            return

        pw = pw_entry.get()
        if not user_entry.get().strip() or not pw:
            messagebox.showwarning("Вход с телефона", "Введите пароль вашей учётной записи Microsoft / Windows.")
            return

        resp = pipe_transact(
            {
                "op": "enroll.begin",
                "domain": domain_entry.get().strip(),
                "username": user_entry.get().strip(),
                "password": pw,
                "mode": "split_key",
                "skip_verify": "true" if skip_verify_var.get() else "false",
            },
            timeout_ms=8000,
            auto_start=True,
        )
        if not resp.get("ok"):
            messagebox.showerror(
                "Ошибка проверки пароля",
                str(resp.get("message") or "Windows отклонила пароль учётной записи."),
            )
            return
        pw_entry.delete(0, "end")
        uri = build_enroll_uri(
            config,
            8765,
            resp,
            phone_pin=phone_pin,
            host_override=server_host_entry.get().strip(),
        )
        enroll_code_var.set(uri)
        window.clipboard_clear()
        window.clipboard_append(uri)
        pin_note = f" + Единый PIN ({config.get('pin', '')})" if phone_pin else " + Биометрия"
        status_var.set(f"✓ Готово ({resp.get('qualified_user')}{pin_note}). Код скопирован в буфер (действует 5 мин)!")
        status_lbl.configure(foreground="#3DD68C")
        show_qr_modal(
            uri,
            "QR-код и код привязки",
            "Отсканируйте QR или вставьте скопированный код в приложении (Привязать вход с телефона).",
        )

    def revoke_enrollment() -> None:
        if not is_win:
            return
        resp = pipe_transact({"op": "enroll.revoke"}, timeout_ms=4000, auto_start=True)
        enroll_code_var.set("")
        refresh_unlock_status()
        if resp.get("ok"):
            messagebox.showinfo("Привязка отозвана", "Привязка телефона и зашифрованный ключ удалены с ПК.")

    btn_row = ttk.Frame(unlock_tab, style="Card.TFrame")
    btn_row.pack(fill="x", pady=(8, 6))
    ttk.Button(
        btn_row,
        text="✨ Сохранить PIN и создать код / QR привязки",
        style="Accent.TButton",
        command=start_enrollment,
    ).pack(side="left", fill="x", expand=True, padx=(0, 8))
    ttk.Button(btn_row, text="Обновить", style="Secondary.TButton", command=lambda: (refresh_readiness(), refresh_unlock_status())).pack(side="left", padx=(0, 8))
    if is_win:
        ttk.Button(btn_row, text="Отозвать", style="Secondary.TButton", command=revoke_enrollment).pack(side="left")

    ttk.Label(
        unlock_tab,
        text="Одноразовый код привязки для телефона (pcphone://enroll?...):",
        style="Card.TLabel",
    ).pack(anchor="w", pady=(8, 4))
    enroll_entry = ttk.Entry(unlock_tab, textvariable=enroll_code_var, state="readonly")
    enroll_entry.pack(fill="x")

    def copy_enroll_code() -> None:
        val = enroll_code_var.get().strip()
        if not val:
            messagebox.showwarning("Код привязки", "Сначала нажмите кнопку создания кода выше.")
            return
        window.clipboard_clear()
        window.clipboard_append(val)
        messagebox.showinfo("Скопировано", "Код привязки скопирован в буфер обмена.")

    sub_btn_row = ttk.Frame(unlock_tab, style="Card.TFrame")
    sub_btn_row.pack(fill="x", pady=(8, 6))
    ttk.Button(sub_btn_row, text="Скопировать код", style="Secondary.TButton", command=copy_enroll_code).pack(side="left", fill="x", expand=True, padx=(0, 8))
    ttk.Button(
        sub_btn_row,
        text="📱 QR-код быстрого добавления / iPhone",
        style="Secondary.TButton",
        command=lambda: show_qr_modal(
            enroll_code_var.get().strip() or setup_uri(str(config.get("pin", "")), 8765, socket.gethostname() or "My PC"),
            "QR-код для телефона",
            f"PIN сервера: {config.get('pin', '')}\nВеб/iPhone версия: {preferred_host(8765)}/app",
        ),
    ).pack(side="left", fill="x", expand=True)

    if is_win:
        ttk.Button(
            unlock_tab,
            text="🛡 Установить модуль экрана блокировки Windows (1 раз от Администратора)",
            style="Secondary.TButton",
            command=install_lockscreen_provider,
        ).pack(fill="x", pady=(4, 0))

    # ===================================================== TAB 2: Подключение, Автозапуск, iOS и RDP
    conn_tab = ttk.Frame(notebook, style="Card.TFrame", padding=18)
    notebook.add(conn_tab, text="  Подключение, iOS и RDP  ")

    def toggle_autostart() -> None:
        if autostart_is_enabled():
            autostart_disable()
            messagebox.showinfo("Автозагрузка", "Автозапуск при старте системы отключён.")
        else:
            autostart_enable()
            messagebox.showinfo("Автозагрузка", "Автозапуск включён! Сервер будет запускаться автоматически при входе.")
        update_autostart_btn()
        refresh_readiness()

    autostart_btn_text = tk.StringVar()

    def update_autostart_btn() -> None:
        autostart_btn_text.set(
            "🟢 Автозапуск при старте системы: ВКЛЮЧЁН (нажмите, чтобы выключить)"
            if autostart_is_enabled()
            else "⚪ Автозапуск при старте системы: ВЫКЛЮЧЕН (нажмите, чтобы включить)"
        )

    update_autostart_btn()
    ttk.Button(conn_tab, textvariable=autostart_btn_text, style="Secondary.TButton", command=toggle_autostart).pack(fill="x", pady=(0, 10))

    ttk.Label(
        conn_tab,
        text=f"Адрес ПК: {preferred_host(8765)}  |  iPhone Safari: {preferred_host(8765)}/app  |  MAC: {primary_mac_address() or '—'}",
        style="Card.TLabel",
        font=("Segoe UI", 9, "bold"),
        wraplength=700,
    ).pack(anchor="w")

    ttk.Label(conn_tab, text="Единый PIN-код подключения (используется и на телефоне, и на сервере):", style="Card.TLabel", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 3))
    pin_entry = ttk.Entry(conn_tab, font=("Segoe UI", 11, "bold"))
    pin_entry.insert(0, str(config.get("pin", "")))
    pin_entry.pack(fill="x")

    def copy_setup() -> None:
        curr_pin = pin_entry.get().strip() or str(config.get("pin", ""))
        if curr_pin != config.get("pin", ""):
            persist_unified_pin(curr_pin)
        uri = setup_uri(curr_pin, 8765, socket.gethostname() or "My PC")
        window.clipboard_clear()
        window.clipboard_append(uri)
        show_qr_modal(uri, "Подключение телефона (Android / iPhone)", f"Единый PIN: {curr_pin}\niPhone App: {preferred_host(8765)}/app")

    ttk.Button(conn_tab, text="📱 Показать QR-код подключения + скопировать ссылку", style="Accent.TButton", command=copy_setup).pack(
        fill="x", pady=10
    )

    fields: dict[str, ttk.Entry] = {}
    rdp = config.get("rdp", {})
    spec = [
        ("host", "Адрес ПК для RDP (необязательно)", ""),
        ("port", "Порт удалённого рабочего стола", 3389),
        ("username", "Имя пользователя для RDP", ""),
        ("gateway", "RD Gateway (необязательно)", ""),
    ]
    for key, label, default in spec:
        ttk.Label(conn_tab, text=label, style="Card.TLabel").pack(anchor="w", pady=(6, 2))
        field = ttk.Entry(conn_tab)
        field.insert(0, str(rdp.get(key, default)))
        field.pack(fill="x")
        fields[key] = field

    def save() -> None:
        try:
            values = {k: v.get().strip() for k, v in fields.items()}
            values["port"] = int(values["port"])
            if not 1 <= values["port"] <= 65535 or "/" in values["host"]:
                raise ValueError()
            latest = load_config()
            new_pin = pin_entry.get().strip()
            if new_pin:
                latest["pin"] = new_pin
                phone_pin_entry.delete(0, "end")
                phone_pin_entry.insert(0, new_pin)
            latest["rdp"] = values
            latest["mac"] = primary_mac_address()
            temp = ROOT / "config.json.tmp"
            temp.write_text(json.dumps(latest, ensure_ascii=False, indent=2), "utf-8")
            temp.replace(ROOT / "config.json")
            config.update(latest)
            messagebox.showinfo("Сохранено", "Настройки сохранены и сразу применены сервером.")
        except (ValueError, OSError):
            messagebox.showerror("Ошибка", "Проверьте адрес, порт и доступ к папке приложения.")

    ttk.Button(conn_tab, text="Сохранить настройки", style="Accent.TButton", command=save).pack(fill="x", pady=12)

    ttk.Button(
        conn_tab,
        text="📂 Открыть папку принятых файлов с телефона (Загрузки/PCPhoneRemote)",
        style="Secondary.TButton",
        command=lambda: _open_folder_native(Path.home() / "Downloads" / "PCPhoneRemote"),
    ).pack(fill="x", pady=(0, 8))
    if is_win:
        ttk.Button(
            conn_tab,
            text="Открыть настройки удалённого рабочего стола Windows",
            style="Secondary.TButton",
            command=lambda: os.startfile("ms-settings:remotedesktop"),
        ).pack(fill="x")

    refresh_readiness()
    refresh_unlock_status()
    window.mainloop()


if __name__ == "__main__":
    main()
