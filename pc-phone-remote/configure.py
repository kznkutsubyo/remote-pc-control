"""Local desktop setup & Windows Phone Sign-In enrollment wizard. Run with pythonw to avoid a console window."""
from __future__ import annotations

import base64
import ctypes
import getpass
import hashlib
import hmac
import json
import os
import secrets
import socket
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import urlencode, urlparse

from app import preferred_host, setup_uri
from companion import load_config, primary_mac_address
from unlock_ipc import pipe_transact

ROOT = Path(__file__).resolve().parent


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    cleaned = text.strip()
    pad = "=" * ((4 - len(cleaned) % 4) % 4)
    return base64.urlsafe_b64decode(cleaned + pad)


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


def main() -> None:
    config = load_config()
    window = tk.Tk()
    window.title("PC Remote — Настройка ПК и вход с телефона")
    window.geometry("750x800")
    window.minsize(660, 740)
    window.configure(bg="#0B0B10")

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

    ttk.Label(outer, text="PC Remote", font=("Segoe UI", 21, "bold")).pack(anchor="w")
    ttk.Label(
        outer,
        text="Привязка телефона, вход в Windows по PIN / биометрии и параметры подключения",
        foreground="#8C8C99",
    ).pack(anchor="w", pady=(2, 12))

    notebook = ttk.Notebook(outer)
    notebook.pack(fill="both", expand=True)

    # ===================================================== TAB 1: Вход в Windows с телефона
    unlock_tab = ttk.Frame(notebook, style="Card.TFrame", padding=18)
    notebook.add(unlock_tab, text="  Вход в Windows с телефона  ")

    default_domain = os.environ.get("USERDOMAIN", socket.gethostname())
    default_user = getpass.getuser()

    # Auto-detect Microsoft Account (USER_INFO_24) from PhoneUnlockService
    acct_info = pipe_transact({"op": "account.detect", "username": default_user}, timeout_ms=3000, auto_start=True)
    is_msa = bool(acct_info.get("is_msa"))
    msa_provider = str(acct_info.get("msa_provider") or "MicrosoftAccount")
    msa_principal = str(acct_info.get("msa_principal") or "")

    ttk.Label(
        unlock_tab,
        text="Шаг 1 · Подтвердите пароль учётной записи и задайте PIN для телефона",
        style="Card.TLabel",
        font=("Segoe UI", 11, "bold"),
    ).pack(anchor="w")

    banner = ttk.Frame(unlock_tab, style="Banner.TFrame", padding=10)
    banner.pack(fill="x", pady=(8, 10))
    if is_msa and msa_principal:
        banner_text = (
            f"⚡ У вас подключена учётная запись Microsoft: {msa_principal} (локальный профиль «{default_user}»).\n"
            "• В поле «Пароль аккаунта» введите ПАРОЛЬ от этой почты Microsoft (короткий PIN от экрана Windows "
            "хранится в чипе TPM и не принимается системой как пароль — это и вызывало ошибку 1326).\n"
            "• А свой привычный короткий PIN-код впишите в поле «PIN-код для телефона» ниже — именно его вы "
            "будете вводить на смартфоне для разблокировки ПК!"
        )
    else:
        banner_text = (
            "• В поле «Пароль аккаунта» введите пароль вашей учётной записи Windows (не PIN Windows Hello).\n"
            "• В поле «PIN-код для телефона» укажите удобный вам пинкод (например, 4–6 цифр), чтобы вводить его "
            "на телефоне для разблокировки ПК (или оставьте пустым для входа по отпечатку пальца)."
        )
    ttk.Label(banner, text=banner_text, style="Banner.TLabel", wraplength=660, justify="left").pack(anchor="w")

    status_var = tk.StringVar(value="Проверка статуса службы входа…")
    status_lbl = ttk.Label(unlock_tab, textvariable=status_var, style="Card.TLabel", foreground="#3DD68C", wraplength=660)
    status_lbl.pack(anchor="w", pady=(0, 8))

    form_grid = ttk.Frame(unlock_tab, style="Card.TFrame")
    form_grid.pack(fill="x", pady=2)

    ttk.Label(form_grid, text="Домен / Провайдер:", style="Card.TLabel").grid(row=0, column=0, sticky="w", pady=4)
    domain_entry = ttk.Entry(form_grid, width=32)
    domain_entry.insert(0, msa_provider if (is_msa and msa_principal) else default_domain)
    domain_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=4)

    ttk.Label(form_grid, text="Аккаунт Windows / Email:", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=4)
    user_entry = ttk.Entry(form_grid, width=32)
    user_entry.insert(0, msa_principal if (is_msa and msa_principal) else default_user)
    user_entry.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=4)

    pw_label_text = "Пароль от аккаунта Microsoft:" if is_msa else "Пароль учётной записи Windows:"
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

    ttk.Label(form_grid, text="PIN-код для телефона (по желанию):", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=4)
    phone_pin_entry = ttk.Entry(form_grid, width=32)
    phone_pin_entry.grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=4)

    ttk.Label(
        form_grid,
        text="Оставьте пустым для входа по биометрии, либо укажите свой пинкод (например 4–6 цифр), чтобы вводить его на телефоне.",
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
    ttk.Checkbutton(
        unlock_tab,
        text="Сохранить без локальной проверки кэша Windows (включите, если на ПК раньше входили ТОЛЬКО по PIN-коду)",
        variable=skip_verify_var,
        style="Card.TCheckbutton",
    ).pack(anchor="w", pady=(6, 4))

    form_grid.columnconfigure(1, weight=1)

    enroll_code_var = tk.StringVar(value="")

    def refresh_unlock_status() -> None:
        resp = pipe_transact({"op": "unlock.status"}, timeout_ms=2500, auto_start=True)
        if not resp.get("ok"):
            status_var.set("Служба входа не отвечает: " + str(resp.get("message", "")))
            status_lbl.configure(foreground="#FF7A85")
            return
        prov_ok = bool(resp.get("provider_installed"))
        prov_note = (
            " | Модуль экрана блокировки (LogonUI): установлен ✓"
            if prov_ok
            else " | ⚠ Модуль экрана блокировки ещё не установлен (нажмите кнопку ниже)"
        )
        if resp.get("enrolled"):
            status_var.set(
                f"✓ Телефон привязан: {resp.get('device_name')} · {resp.get('qualified_user')}{prov_note}"
            )
            status_lbl.configure(foreground="#3DD68C" if prov_ok else "#F5B14C")
        else:
            status_var.set("Телефон ещё не привязан для входа в Windows. Заполните форму ниже." + prov_note)
            status_lbl.configure(foreground="#F5B14C")

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
            "Запущена установка системного модуля PhoneUnlockProvider.dll и службы PhoneUnlockService.\n\n"
            "Дождитесь закрытия окна PowerShell (2–3 секунды) и нажмите ОК — статус обновится автоматически!",
        )
        refresh_unlock_status()

    def start_enrollment() -> None:
        pw = pw_entry.get()
        phone_pin = phone_pin_entry.get().strip()
        if not user_entry.get().strip() or not pw:
            messagebox.showwarning("Вход с телефона", "Введите пароль вашей учётной записи Microsoft / Windows.")
            return
        if phone_pin and len(phone_pin) < 4:
            messagebox.showwarning("PIN-код для телефона", "PIN-код для телефона должен содержать минимум 4 символа (или оставьте поле пустым).")
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
        pin_note = f" + PIN на телефоне ({len(phone_pin)} симв.)" if phone_pin else " + Биометрия"
        status_var.set(
            f"Готово ({resp.get('qualified_user')}{pin_note}). Код привязки скопирован в буфер (действует 5 мин)!"
        )
        status_lbl.configure(foreground="#3DD68C")
        messagebox.showinfo(
            "Шаг 2 · Привяжите телефон",
            "Учётная запись успешно подготовлена!\n\n"
            "Одноразовый код pcphone://enroll?... уже скопирован в буфер обмена.\n"
            "Откройте приложение на телефоне → «Привязать вход с телефона» → Вставьте код.",
        )

    def revoke_enrollment() -> None:
        resp = pipe_transact({"op": "enroll.revoke"}, timeout_ms=4000, auto_start=True)
        enroll_code_var.set("")
        refresh_unlock_status()
        if resp.get("ok"):
            messagebox.showinfo("Привязка отозвана", "Привязка телефона и зашифрованный ключ удалены с ПК.")

    btn_row = ttk.Frame(unlock_tab, style="Card.TFrame")
    btn_row.pack(fill="x", pady=(8, 6))
    ttk.Button(
        btn_row,
        text="Создать код привязки входа",
        style="Accent.TButton",
        command=start_enrollment,
    ).pack(side="left", fill="x", expand=True, padx=(0, 8))
    ttk.Button(btn_row, text="Обновить статус", style="Secondary.TButton", command=refresh_unlock_status).pack(side="left", padx=(0, 8))
    ttk.Button(btn_row, text="Отозвать", style="Secondary.TButton", command=revoke_enrollment).pack(side="left")

    ttk.Label(
        unlock_tab,
        text="Шаг 2 · Одноразовый код привязки для телефона (pcphone://enroll?...):",
        style="Card.TLabel",
    ).pack(anchor="w", pady=(8, 4))
    enroll_entry = ttk.Entry(unlock_tab, textvariable=enroll_code_var, state="readonly")
    enroll_entry.pack(fill="x")

    def copy_enroll_code() -> None:
        val = enroll_code_var.get().strip()
        if not val:
            messagebox.showwarning("Код привязки", "Сначала нажмите «Создать код привязки входа».")
            return
        window.clipboard_clear()
        window.clipboard_append(val)
        messagebox.showinfo("Скопировано", "Одноразовый код привязки входа скопирован в буфер обмена.")

    ttk.Button(
        unlock_tab,
        text="Скопировать одноразовый код привязки входа",
        style="Secondary.TButton",
        command=copy_enroll_code,
    ).pack(fill="x", pady=(8, 6))

    ttk.Button(
        unlock_tab,
        text="🛡 Установить модуль экрана блокировки Windows (1 раз от Администратора)",
        style="Secondary.TButton",
        command=install_lockscreen_provider,
    ).pack(fill="x", pady=(0, 0))

    # ===================================================== TAB 2: Подключение и RDP
    conn_tab = ttk.Frame(notebook, style="Card.TFrame", padding=18)
    notebook.add(conn_tab, text="  Подключение и RDP  ")

    ttk.Label(
        conn_tab,
        text="Адрес сервера: " + preferred_host(8765) + "   |   MAC (WoL): " + (primary_mac_address() or "—"),
        style="Card.TLabel",
        font=("Segoe UI", 10, "bold"),
    ).pack(anchor="w")

    def copy_setup() -> None:
        window.clipboard_clear()
        window.clipboard_append(setup_uri(str(config.get("pin", "")), 8765))
        messagebox.showinfo("Подключение", "Код подключения скопирован. На телефоне: Настройки → Импорт кода.")

    ttk.Button(conn_tab, text="Скопировать базовый код подключения телефона", style="Accent.TButton", command=copy_setup).pack(
        fill="x", pady=12
    )

    fields: dict[str, ttk.Entry] = {}
    rdp = config.get("rdp", {})
    spec = [
        ("host", "Адрес ПК для RDP (необязательно)", ""),
        ("port", "Порт удалённого рабочего стола", 3389),
        ("username", "Имя пользователя Windows для RDP", ""),
        ("gateway", "RD Gateway (необязательно)", ""),
    ]
    for key, label, default in spec:
        ttk.Label(conn_tab, text=label, style="Card.TLabel").pack(anchor="w", pady=(8, 3))
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
            latest["rdp"] = values
            latest["mac"] = primary_mac_address()
            temp = ROOT / "config.json.tmp"
            temp.write_text(json.dumps(latest, ensure_ascii=False, indent=2), "utf-8")
            temp.replace(ROOT / "config.json")
            config.update(latest)
            messagebox.showinfo("Сохранено", "Настройки сохранены. Сервер применит их при следующем запросе.")
        except (ValueError, OSError):
            messagebox.showerror("Ошибка", "Проверьте адрес, порт и доступ к папке приложения.")

    ttk.Button(conn_tab, text="Сохранить настройки", style="Accent.TButton", command=save).pack(fill="x", pady=14)

    def open_received_files() -> None:
        dl = Path.home() / "Downloads" / "PCPhoneRemote"
        dl.mkdir(parents=True, exist_ok=True)
        os.startfile(str(dl))

    ttk.Button(
        conn_tab,
        text="📂 Открыть папку принятых файлов с телефона (Загрузки\\PCPhoneRemote)",
        style="Secondary.TButton",
        command=open_received_files,
    ).pack(fill="x", pady=(0, 8))
    ttk.Button(
        conn_tab,
        text="Открыть настройки удалённого рабочего стола Windows",
        style="Secondary.TButton",
        command=lambda: os.startfile("ms-settings:remotedesktop"),
    ).pack(fill="x")

    refresh_unlock_status()
    window.mainloop()


if __name__ == "__main__":
    main()
