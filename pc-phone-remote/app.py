from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import hmac
import html
import http.cookies
import io
import ipaddress
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlencode, urlparse
from pathlib import Path

from companion import (
    Companion,
    FeatureError,
    MAX_BODY,
    control_windows_audio,
    load_config,
    primary_mac_address,
    run_on_input_desktop,
)
from desktop_ui import desktop_html_bytes
from ios_pwa import pwa_html_bytes, pwa_manifest_bytes, pwa_service_worker_bytes
from linux_support import linux_run_power_command
from pro_features import (
    APP_VERSION,
    HOTKEYS,
    autofix_wol_windows,
    capture_screen_jpeg,
    check_github_updates,
    diagnose_wol,
    sanitize_custom_buttons,
    run_custom_button,
)
from tls_helper import (
    CERT_FILE,
    ensure_local_tls_cert,
    tls_status_snapshot,
    wrap_server_ssl,
)
from unlock_ipc import pipe_transact

try:
    import psutil
except ImportError:
    psutil = None

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
LOGIN_FAILURES: dict[str, list[float]] = {}
LOCAL_ADMIN_TOKEN = secrets.token_urlsafe(24)
SERVER_START_TIME = time.time()
LAST_CLIENT_SEEN: dict[str, object] = {}


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


def outbound_ip() -> str:
    for probe in (("8.8.8.8", 80), ("1.1.1.1", 80), ("192.168.1.1", 80)):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(probe)
                candidate = sock.getsockname()[0]
                ip = ipaddress.ip_address(candidate)
                if not ip.is_loopback and not ip.is_unspecified:
                    return candidate
        except (OSError, ValueError):
            continue
    return ""


def preferred_host(port: int) -> str:
    fallback = f"http://127.0.0.1:{port}"
    # Prefer the real interface that owns the OS default route (avoids Hyper-V / WSL / Docker 172.x vEthernet switches).
    routed = outbound_ip()
    if routed:
        return f"http://{routed}:{port}"

    lan_172 = ipaddress.ip_network("172.16.0.0/12")
    for skip_virtual_172 in (True, False):
        for address in local_addresses(port):
            parsed = urlparse(address)
            host = parsed.hostname or ""
            try:
                ip = ipaddress.ip_address(host)
            except ValueError:
                continue
            if ip.is_private and not ip.is_loopback:
                if skip_virtual_172 and ip in lan_172:
                    continue
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


def qr_png_bytes(value: str) -> bytes:
    """Render a PNG QR code offline using the bundled qrcode + Pillow libraries."""
    if qrcode is None or not value:
        return b""
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(value)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#09090D", back_color="#FFFFFF")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def ordered_lan_ips(port: int) -> list[str]:
    ips: list[str] = []
    routed = outbound_ip()
    if routed:
        ips.append(routed)
    for address in local_addresses(port):
        host = urlparse(address).hostname or ""
        try:
            ip_obj = ipaddress.ip_address(host)
        except ValueError:
            continue
        if not ip_obj.is_loopback and host not in ips:
            ips.append(host)
    if not ips:
        ips.append("127.0.0.1")
    return ips


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    cleaned = text.strip()
    pad = "=" * ((4 - len(cleaned) % 4) % 4)
    return base64.urlsafe_b64decode(cleaned + pad)


def _build_enroll_uri(config: dict, port: int, enroll_resp: dict, phone_pin: str = "", host_override: str = "") -> str:
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


def local_admin_snapshot(server, port: int) -> dict:
    from autostart import is_enabled as autostart_is_enabled

    comp: Companion = server.companion
    cfg_path: Path = getattr(server, "config_path", None) or Path(__file__).with_name("config.json")
    cfg = dict(comp.config) if isinstance(comp.config, dict) else {}
    if cfg_path.exists():
        try:
            loaded = json.loads(cfg_path.read_text("utf-8"))
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except Exception:
            pass

    active_pin = str(getattr(server, "pin", "") or cfg.get("pin", ""))
    ips = ordered_lan_ips(port)
    selected_host = ips[0] if ips else "127.0.0.1"
    mac = str(cfg.get("mac") or primary_mac_address() or "")
    hostname = socket.gethostname() or "My PC"
    rdp = cfg.get("rdp", {}) if isinstance(cfg.get("rdp"), dict) else {}

    # Non-blocking unlock snapshot
    unlock_snap = comp.unlock_status_snapshot(auto_start=False)
    pipe_running = bool(unlock_snap.get("available"))
    unlock_installed = bool(unlock_snap.get("provider_installed"))
    unlock_enrolled = bool(unlock_snap.get("enrolled"))
    if os.name != "nt":
        unlock_details = "Linux logind / PAM"
    elif unlock_installed:
        unlock_details = f"PhoneUnlockProvider.dll ({unlock_snap.get('qualified_user') or 'готов'})"
    else:
        unlock_details = "Модуль LogonUI не зарегистрирован"

    # Telemetry
    telemetry = {"cpu_percent": 0.0, "memory_percent": 0.0, "memory_used_gb": 0.0, "memory_total_gb": 0.0, "disk_percent": 0.0}
    try:
        du = shutil.disk_usage(comp.root)
        telemetry["disk_percent"] = round((du.used / du.total) * 100.0, 1) if du.total else 0.0
    except Exception:
        pass
    if psutil is not None:
        try:
            vm = psutil.virtual_memory()
            telemetry["cpu_percent"] = float(psutil.cpu_percent(interval=None))
            telemetry["memory_percent"] = float(vm.percent)
            telemetry["memory_used_gb"] = round((vm.total - vm.available) / (1024 ** 3), 1)
            telemetry["memory_total_gb"] = round(vm.total / (1024 ** 3), 1)
        except Exception:
            pass

    # Shared files & note
    files = []
    try:
        for p in sorted(comp.root.iterdir(), key=lambda x: x.name.casefold()):
            if p.is_file() and not p.is_symlink() and not p.name.startswith(".") and p.name != "shared-note.txt":
                st = p.stat()
                files.append({"name": p.name, "size": st.st_size, "mtime": int(st.st_mtime)})
    except Exception:
        pass
    note_text = ""
    try:
        note_p = comp.file_path("shared-note.txt")
        if note_p.exists() and note_p.stat().st_size <= 65536:
            note_text = note_p.read_text("utf-8", errors="replace")
    except Exception:
        pass

    with SESSIONS_LOCK:
        last_seen = dict(LAST_CLIENT_SEEN) if LAST_CLIENT_SEEN else None
    if last_seen and isinstance(last_seen.get("ts"), (int, float)):
        last_seen["ago_sec"] = max(0.0, round(time.time() - float(last_seen["ts"]), 1))

    autostart_on = False
    try:
        autostart_on = autostart_is_enabled()
    except Exception:
        pass

    return {
        "ok": True,
        "app_version": APP_VERSION,
        "os": "windows" if os.name == "nt" else "linux",
        "hostname": hostname,
        "port": port,
        "pin": active_pin,
        "mac": mac,
        "selected_host": selected_host,
        "ips": ips,
        "share_dir": str(comp.root),
        "rdp_host": str(rdp.get("host", "")),
        "rdp_port": int(rdp.get("port", 3389) or 3389),
        "rdp_username": str(rdp.get("username", "")),
        "rdp_gateway": str(rdp.get("gateway", "")),
        "autostart_enabled": autostart_on,
        "autostart_method": "Windows Registry Run" if os.name == "nt" else "systemd --user / XDG autostart",
        "unlock_provider_installed": unlock_installed,
        "unlock_enrolled": unlock_enrolled,
        "unlock_provider_details": unlock_details,
        "pipe_running": pipe_running,
        "telemetry": telemetry,
        "last_client_seen": last_seen,
        "files": files,
        "note": note_text,
        "custom_buttons": sanitize_custom_buttons(cfg.get("custom_buttons")),
        "hotkeys": sorted(HOTKEYS.keys()),
        "https_enabled": bool(cfg.get("https_enabled", False)),
        "tls_active": bool(getattr(server, "https_enabled", False)),
        "tls": tls_status_snapshot(),
        "server_uptime_sec": max(0, int(time.time() - SERVER_START_TIME)),
    }


def handle_local_admin_action(server, port: int, payload: dict) -> dict:
    from autostart import disable as autostart_disable, enable as autostart_enable

    action = str(payload.get("action") or "")
    comp: Companion = server.companion
    cfg_path: Path = getattr(server, "config_path", None) or Path(__file__).with_name("config.json")

    if action == "save_config":
        cfg = json.loads(cfg_path.read_text("utf-8")) if cfg_path.exists() else {}
        if not isinstance(cfg, dict):
            cfg = {}
        new_pin = str(payload.get("pin", "")).strip()
        if new_pin:
            cfg["pin"] = new_pin
            cfg.pop("allowed_pins", None)
        share_dir = str(payload.get("share_dir", "")).strip()
        if share_dir:
            resolved = Path(share_dir).expanduser().resolve()
            resolved.mkdir(parents=True, exist_ok=True)
            cfg["share_dir"] = str(resolved)
            comp.root = resolved
        elif "share_dir" in cfg:
            cfg.pop("share_dir", None)
        rdp = cfg.get("rdp", {}) if isinstance(cfg.get("rdp"), dict) else {}
        rdp["host"] = str(payload.get("rdp_host", rdp.get("host", ""))).strip()
        rdp["port"] = int(payload.get("rdp_port", rdp.get("port", 3389)) or 3389)
        rdp["username"] = str(payload.get("rdp_username", rdp.get("username", ""))).strip()
        rdp["gateway"] = str(payload.get("rdp_gateway", rdp.get("gateway", ""))).strip()
        cfg["rdp"] = rdp
        cfg["mac"] = primary_mac_address() or str(cfg.get("mac", ""))
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cfg_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(cfg_path)
        comp.config.update(cfg)
        if new_pin:
            server.pin = new_pin
            with SESSIONS_LOCK:
                SESSIONS.clear()
        return {"ok": True, "message": "Настройки сохранены"}

    if action == "set_autostart":
        if bool(payload.get("enabled")):
            autostart_enable()
            return {"ok": True, "enabled": True, "message": "✅ Автозапуск включён"}
        autostart_disable()
        return {"ok": True, "enabled": False, "message": "Автозапуск отключён"}

    if action == "open_firewall":
        req_port = int(payload.get("port") or port or 8765)
        if os.name == "nt":
            ps_cmd = (
                f"netsh advfirewall firewall delete rule name='PC Phone Remote TCP' > $null 2>&1; "
                f"netsh advfirewall firewall add rule name='PC Phone Remote TCP' dir=in action=allow protocol=TCP localport={req_port} profile=any; "
                f"netsh advfirewall firewall delete rule name='PC Phone Remote UDP' > $null 2>&1; "
                f"netsh advfirewall firewall add rule name='PC Phone Remote UDP' dir=in action=allow protocol=UDP localport=8766 profile=any"
            )
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", "powershell.exe", f"-NoProfile -Command \"{ps_cmd}\"", None, 0
            )
            return {"ok": True, "message": f"🛡 Правила брандмауэра запрошены для TCP {req_port} / UDP 8766"}
        for fw_cmd in (
            ["ufw", "allow", f"{req_port}/tcp"],
            ["ufw", "allow", "8766/udp"],
            ["firewall-cmd", "--permanent", f"--add-port={req_port}/tcp"],
            ["firewall-cmd", "--permanent", "--add-port=8766/udp"],
            ["firewall-cmd", "--reload"],
        ):
            subprocess.run(fw_cmd, capture_output=True, check=False)
        return {"ok": True, "message": f"🛡 Правила применены (ufw/firewalld) для {req_port}"}

    if action == "install_unlock_provider":
        if os.name != "nt":
            return {"ok": True, "message": "На Linux используется нативный logind / PAM."}
        app_root = Path(__file__).resolve().parent
        candidates = [
            app_root / "windows-unlock" / "install-unlock.ps1",
            app_root.parent / "windows-unlock" / "install-unlock.ps1",
        ]
        script = next((c for c in candidates if c.exists()), None)
        if script is None:
            return {"ok": False, "error": "Скрипт windows-unlock/install-unlock.ps1 не найден."}
        params = f'-NoProfile -ExecutionPolicy Bypass -File "{script}"'
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", params, str(script.parent), 1)
        if rc <= 32:
            return {"ok": False, "error": "Установка отменена (UAC отклонён)."}
        return {"ok": True, "message": "✅ Запущена установка Credential Provider (подтвердите UAC)"}

    if action == "enroll_begin":
        domain = str(payload.get("domain") or ".").strip() or "."
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        host_override = str(payload.get("host") or "").strip()
        if not username or not password:
            return {"ok": False, "error": "Укажите имя пользователя и пароль Windows."}
        resp = pipe_transact(
            {
                "op": "enroll.begin",
                "domain": domain,
                "username": username,
                "password": password,
                "mode": "split_key",
            },
            timeout_ms=8000,
            auto_start=True,
        )
        if not resp.get("ok"):
            return {"ok": False, "error": str(resp.get("message") or "Неверный пароль или служба недоступна")}
        uri = _build_enroll_uri(comp.config, port, resp, phone_pin=str(getattr(server, "pin", "")), host_override=host_override)
        return {"ok": True, "qr_uri": uri, "qualified_user": resp.get("qualified_user", "")}

    if action == "enroll_revoke":
        if os.name == "nt":
            resp = pipe_transact({"op": "enroll.revoke"}, timeout_ms=4000, auto_start=True)
            return {"ok": bool(resp.get("ok", True)), "message": "Привязка отозвана"}
        return {"ok": True, "message": "OK"}

    if action == "open_shared_folder":
        return comp.dispatch({"action": "files.open_folder"})

    if action == "note_set":
        return {"ok": True, **comp.dispatch({"action": "note.set", "text": str(payload.get("text") or "")})}

    if action == "custom_buttons_save":
        buttons = sanitize_custom_buttons(payload.get("buttons"))
        cfg = json.loads(cfg_path.read_text("utf-8")) if cfg_path.exists() else {}
        if not isinstance(cfg, dict):
            cfg = {}
        cfg["custom_buttons"] = buttons
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cfg_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(cfg_path)
        comp.config["custom_buttons"] = buttons
        return {"ok": True, "buttons": buttons, "message": "✅ Кнопки Studio Pro сохранены"}

    if action == "custom_button_test":
        bid = str(payload.get("id") or "").strip()
        buttons = sanitize_custom_buttons(comp.config.get("custom_buttons"))
        btn = next((b for b in buttons if b["id"] == bid), None)
        if not btn:
            return {"ok": False, "error": "Сначала сохраните кнопку"}
        run_custom_button(btn, run_desktop_fn=run_on_input_desktop)
        return {"ok": True, "message": f"▶ Выполнено: {btn['label']}"}

    if action == "wol_diagnose":
        return diagnose_wol()

    if action == "wol_autofix":
        return autofix_wol_windows()

    if action == "check_updates":
        return check_github_updates()

    if action == "tls_toggle":
        enable = bool(payload.get("enabled"))
        regen = bool(payload.get("regen"))
        if enable or regen:
            ensure_local_tls_cert(ordered_lan_ips(port), force_regen=regen)
        cfg = json.loads(cfg_path.read_text("utf-8")) if cfg_path.exists() else {}
        if not isinstance(cfg, dict):
            cfg = {}
        cfg["https_enabled"] = enable
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cfg_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(cfg_path)
        comp.config["https_enabled"] = enable
        return {
            "ok": True,
            "https_enabled": enable,
            "tls": tls_status_snapshot(),
            "message": "✅ HTTPS включён — перезапустите сервер" if enable else "HTTP режим сохранён — перезапустите сервер",
        }

    if action == "restart_server":
        def _restart() -> None:
            time.sleep(0.35)
            exe_candidate = Path(__file__).with_name("PCPhoneRemote.exe")
            if os.name == "nt" and exe_candidate.exists():
                subprocess.Popen(
                    ["cmd.exe", "/c", f'ping -n 2 127.0.0.1 >nul & "{exe_candidate}" --server'],
                    cwd=str(Path(__file__).parent),
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                subprocess.Popen(
                    [sys.executable, "-c", f"import time, subprocess, sys; time.sleep(0.9); subprocess.Popen([sys.executable, {repr(str(Path(__file__).resolve()))}, '--port', {repr(str(port))}])"],
                    cwd=str(Path(__file__).parent),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            server.shutdown()
        threading.Thread(target=_restart, daemon=True).start()
        return {"ok": True, "message": "Перезапуск сервера..."}

    return {"ok": False, "error": f"Unknown action: {action}"}


def enable_shutdown_privilege() -> bool:
    if os.name != "nt":
        return True
    try:
        k32 = ctypes.windll.kernel32
        adv = ctypes.windll.advapi32
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        adv.OpenProcessToken.argtypes = [ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
        hToken = ctypes.c_void_p()
        if not adv.OpenProcessToken(k32.GetCurrentProcess(), 0x0020 | 0x0008, ctypes.byref(hToken)):
            return False

        class LUID(ctypes.Structure):
            _fields_ = [("LowPart", ctypes.wintypes.DWORD), ("HighPart", ctypes.wintypes.LONG)]
        class LUID_AND_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("Luid", LUID), ("Attributes", ctypes.wintypes.DWORD)]
        class TOKEN_PRIVILEGES(ctypes.Structure):
            _fields_ = [("PrivilegeCount", ctypes.wintypes.DWORD), ("Privileges", LUID_AND_ATTRIBUTES * 1)]

        luid = LUID()
        if adv.LookupPrivilegeValueW(None, "SeShutdownPrivilege", ctypes.byref(luid)):
            tp = TOKEN_PRIVILEGES()
            tp.PrivilegeCount = 1
            tp.Privileges[0].Luid = luid
            tp.Privileges[0].Attributes = 0x00000002  # SE_PRIVILEGE_ENABLED
            adv.AdjustTokenPrivileges(hToken, False, ctypes.byref(tp), 0, None, None)
        k32.CloseHandle(hToken)
        return True
    except Exception:
        return False


def discovery_payload(http_port: int = 8765, https_enabled: bool = False) -> dict:
    """Return LAN discovery metadata JSON for automatic phone scanning."""
    parsed = urlparse(preferred_host(http_port))
    return {
        "ok": True,
        "service": "pc-phone-remote",
        "version": APP_VERSION,
        "https": bool(https_enabled),
        "name": socket.gethostname() or "My PC",
        "host": parsed.hostname or "",
        "port": int(parsed.port or http_port),
        "mac": primary_mac_address() or "",
        "os": "windows" if os.name == "nt" else "linux",
    }


def start_udp_discovery_listener(http_port: int = 8765, udp_port: int = 8766, https_enabled: bool = False) -> threading.Thread:
    """Start a background daemon listening for UDP LAN discovery probes."""
    def _serve_udp() -> None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("0.0.0.0", udp_port))
                while True:
                    try:
                        data, addr = sock.recvfrom(1024)
                    except OSError:
                        break
                    if data.startswith(b"PCPHONE_DISCOVER"):
                        payload = json.dumps(discovery_payload(http_port, https_enabled=https_enabled)).encode("utf-8")
                        try:
                            sock.sendto(payload, addr)
                        except OSError:
                            pass
        except OSError:
            pass

    t = threading.Thread(target=_serve_udp, daemon=True)
    t.start()
    return t


def _asset_bytes(filename: str) -> bytes:
    """Read generated brand asset bytes (png/ico) on demand, generating defaults if missing."""
    asset = Path(__file__).with_name("assets") / filename
    if not asset.exists():
        try:
            from brand_icon import ensure_brand_assets
            ensure_brand_assets()
        except Exception:
            pass
    if asset.exists():
        return asset.read_bytes()
    return b""


def run_command(command: str) -> None:
    if os.name != "nt":
        linux_run_power_command(command)
        return

    if command == "mute":
        if Companion.session_locked():
            raise FeatureError("Media controls require an unlocked Windows session", 409)
        if control_windows_audio("mute") is None:
            def _mute_vk() -> None:
                ctypes.windll.user32.keybd_event(0xAD, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0xAD, 0, 2, 0)
            run_on_input_desktop(_mute_vk)
        return

    if command == "lock":
        locked_ok = False
        def _do_lock() -> None:
            nonlocal locked_ok
            locked_ok = bool(ctypes.windll.user32.LockWorkStation())
        run_on_input_desktop(_do_lock)
        if not locked_ok:
            subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"],
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        return

    if command == "sleep":
        enable_shutdown_privilege()
        try:
            powrprof = ctypes.windll.powrprof
            powrprof.SetSuspendState.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
            powrprof.SetSuspendState.restype = ctypes.c_int
            if powrprof.SetSuspendState(0, 1, 0):
                return
        except Exception:
            pass
        subprocess.Popen(
            ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return

    if command == "restart":
        enable_shutdown_privilege()
        subprocess.run(["shutdown.exe", "/r", "/f", "/t", "0"], check=False, creationflags=subprocess.CREATE_NO_WINDOW)
        return

    if command == "shutdown":
        enable_shutdown_privilege()
        subprocess.run(["shutdown.exe", "/s", "/f", "/t", "0"], check=False, creationflags=subprocess.CREATE_NO_WINDOW)
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
        <p style="margin-top:14px;font-size:13px;"><a href="/app" style="color:var(--accent)">📱 Open Full iOS / Mobile Web App (PWA)</a></p>
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
        <p><a href="/share" style="color:var(--accent)">Files and shared text</a></p>
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
    app_url = f"{preferred_host(port)}/app"
    qr_block = (
        f'<img alt="Pairing QR code" src="{qr_src}" style="width: min(100%, 280px); display: block; margin: 22px auto; background: white; padding: 14px; border-radius: 8px;">'
        if qr_src
        else '<p class="status">Install optional dependencies to show a QR code: <code>pip install -r requirements.txt</code></p>'
    )
    return page_shell(
        f"{APP_NAME} Pairing",
        f"""
        <h1>Pair this PC</h1>
        <p>Scan the QR code in the Android app (<b>Scan QR</b>) or open <a href="{html.escape(app_url)}" style="color:var(--accent)">iPhone / Web PWA</a>.</p>
        {qr_block}
        <p style="margin:12px 0;text-align:center">
          <a href="{html.escape(uri)}" class="primary" style="display:inline-block;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600">Open in App (1-Tap Pair)</a>
          &nbsp;
          <a href="/desktop" style="color:var(--accent);font-size:13px">Control Center UI</a>
        </p>
        <p class="status">Setup code:</p>
        <input value="{html.escape(uri)}" readonly onclick="this.select()">
        <p class="status">Local address: {html.escape(preferred_host(port))}</p>
        """,
    )


class RemoteHandler(BaseHTTPRequestHandler):
    server_version = "PCPhoneRemote/2.0"

    def _is_local_admin_request(self, require_token: bool = False) -> bool:
        if self.client_address[0] not in {"127.0.0.1", "::1"}:
            return False
        host = urlparse("http://" + self.headers.get("Host", "")).hostname
        if host not in {"127.0.0.1", "localhost", "::1"}:
            return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            return False
        origin = self.headers.get("Origin", "")
        if origin:
            origin_host = urlparse(origin).hostname
            if origin_host not in {"127.0.0.1", "localhost", "::1"}:
                return False
        if require_token:
            supplied = self.headers.get("X-Local-Admin", "")
            if not supplied or not secrets.compare_digest(supplied, LOCAL_ADMIN_TOKEN):
                return False
        return True

    def _record_client_seen(self, path: str) -> None:
        with SESSIONS_LOCK:
            LAST_CLIENT_SEEN.update({
                "ip": self.client_address[0],
                "ua": self.headers.get("User-Agent", "")[:120],
                "path": path,
                "ts": time.time(),
            })

    def setup(self):
        super().setup()
        self.connection.settimeout(35)

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
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, status: int, payload: dict) -> None:
        self.send_bytes(status, json.dumps(payload).encode("utf-8"), "application/json")

    def read_body(self, limit: int = MAX_BODY) -> bytes:
        if self.headers.get("Transfer-Encoding"):
            raise FeatureError("Chunked requests are not supported", 400)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise FeatureError("Invalid Content-Length") from None
        if not 0 <= length <= limit:
            raise FeatureError("Request too large", 413)
        data = self.rfile.read(length)
        if len(data) != length:
            raise FeatureError("Incomplete request")
        return data

    def api_request(self) -> dict:
        try:
            payload = json.loads(self.read_body())
        except (ValueError, UnicodeDecodeError):
            raise FeatureError("Invalid JSON") from None
        if not isinstance(payload, dict):
            raise FeatureError("Expected a JSON object")
        return payload

    def redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.send_bytes(200, b"ok", "text/plain; charset=utf-8")
            return

        if parsed.path == "/desktop":
            if not self._is_local_admin_request(require_token=False):
                self.send_json(403, {"message": "Open Desktop Control Center locally on 127.0.0.1"})
                return
            self.send_bytes(200, desktop_html_bytes(LOCAL_ADMIN_TOKEN))
            return

        if parsed.path == "/api/local/qr":
            if not self._is_local_admin_request(require_token=False):
                self.send_json(403, {"message": "Forbidden"})
                return
            data_val = parse_qs(parsed.query).get("data", [""])[0]
            if not data_val or len(data_val) > 2048:
                self.send_json(400, {"message": "Missing or invalid data parameter"})
                return
            png = qr_png_bytes(data_val)
            if not png:
                self.send_json(503, {"message": "QR generator unavailable"})
                return
            self.send_bytes(200, png, "image/png")
            return

        if parsed.path == "/api/local/admin":
            if not self._is_local_admin_request(require_token=False):
                self.send_json(403, {"message": "Forbidden"})
                return
            self.send_json(200, local_admin_snapshot(self.server, self.port))
            return

        if parsed.path == "/api/discover":
            self._record_client_seen("/api/discover")
            self.send_json(200, discovery_payload(self.port, https_enabled=bool(getattr(self.server, "https_enabled", False))))
            return

        if parsed.path == "/api/local/cert":
            if not CERT_FILE.exists():
                self.send_json(404, {"message": "HTTPS certificate not generated yet"})
                return
            cert_data = CERT_FILE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-x509-ca-cert")
            self.send_header("Content-Disposition", 'attachment; filename="pc-phone-remote-local.crt"')
            self.send_header("Content-Length", str(len(cert_data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cert_data)
            return

        if parsed.path == "/api/screen.mjpg":
            if not self.is_authenticated():
                self.send_json(401, {"message": "Not authenticated"})
                return
            comp: Companion = self.server.companion
            if comp.session_locked() is True:
                self.send_json(409, {"message": "Screen stream requires an unlocked session"})
                return
            qs = parse_qs(parsed.query)
            try:
                mon = max(0, min(7, int(qs.get("monitor", ["0"])[0] or 0)))
                fps = max(1, min(5, int(qs.get("fps", ["3"])[0] or 3)))
                qual = max(30, min(80, int(qs.get("q", ["55"])[0] or 55)))
                width = max(480, min(1280, int(qs.get("w", ["900"])[0] or 900)))
            except ValueError:
                mon, fps, qual, width = 0, 3, 55, 900
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
            self.end_headers()
            interval = 1.0 / fps
            try:
                while True:
                    if comp.session_locked() is True:
                        break
                    jpeg, _, _, _ = capture_screen_jpeg(mon, max_width=width, quality=qual)
                    header = (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
                    )
                    self.wfile.write(header + jpeg + b"\r\n")
                    self.wfile.flush()
                    time.sleep(interval)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            except Exception:
                pass
            return

        if parsed.path == "/app":
            self._record_client_seen("/app")
            host_os = "windows" if os.name == "nt" else "linux"
            self.send_bytes(200, pwa_html_bytes(self.is_authenticated(), socket.gethostname() or "My PC", host_os))
            return

        if parsed.path == "/manifest.json":
            self.send_bytes(200, pwa_manifest_bytes(), "application/manifest+json; charset=utf-8")
            return

        if parsed.path == "/sw.js":
            self.send_bytes(200, pwa_service_worker_bytes(), "application/javascript; charset=utf-8")
            return

        if parsed.path in {"/apple-touch-icon.png", "/icon-192.png", "/icon-512.png"}:
            fname = {
                "/apple-touch-icon.png": "apple_touch_icon.png",
                "/icon-192.png": "app_icon_192.png",
                "/icon-512.png": "app_icon_512.png",
            }[parsed.path]
            raw = _asset_bytes(fname)
            if not raw:
                self.send_error(404)
                return
            self.send_bytes(200, raw, "image/png")
            return

        if parsed.path == "/pair":
            if not self._is_local_admin_request(require_token=False):
                self.send_json(403, {"message": "Open pairing on this PC at http://127.0.0.1:" + str(self.port) + "/pair"})
                return
            self.send_bytes(200, pair_page(self.pin, self.port))
            return

        if parsed.path == "/share":
            if not self.is_authenticated():
                self.send_bytes(200, login_page())
            else:
                self.send_bytes(200, Path(__file__).with_name("share.html").read_bytes())
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
        if parsed.path == "/api/local/admin":
            if not self._is_local_admin_request(require_token=True):
                self.send_json(403, {"message": "Forbidden: invalid local admin token or origin"})
                return
            try:
                payload = self.api_request()
                result = handle_local_admin_action(self.server, self.port, payload)
                status_code = 200 if result.get("ok", True) else 400
                self.send_json(status_code, result)
            except FeatureError as exc:
                self.send_json(exc.status, {"ok": False, "error": str(exc)})
            except Exception as exc:
                self.send_json(500, {"ok": False, "error": str(exc)})
            return

        if parsed.path == "/api/v2":
            if not self.is_authenticated():
                self.send_json(401, {"message": "Not authenticated"})
                return
            self._record_client_seen("/api/v2")
            try:
                self.send_json(200, self.server.companion.dispatch(self.api_request()))
            except FeatureError as exc:
                self.send_json(exc.status, {"message": str(exc)})
            except Exception:
                self.send_json(500, {"message": "PC could not complete this operation"})
            return

        try:
            body = self.read_body(8192)
        except FeatureError as exc:
            self.send_json(exc.status, {"message": str(exc)})
            return

        if parsed.path == "/login":
            address = self.client_address[0]
            with SESSIONS_LOCK:
                failures = [at for at in LOGIN_FAILURES.get(address, []) if at > time.time() - 60]
                if len(failures) >= 10:
                    self.send_json(429, {"message": "Too many attempts. Wait one minute."})
                    return
            form = parse_qs(body.decode("utf-8", errors="replace"))
            received_pin = form.get("pin", [""])[0].strip()
            valid_pins = {self.pin.strip()} if self.pin else set()
            comp = getattr(self.server, "companion", None)
            cfg = getattr(comp, "config", None) if comp else None
            cfg_path = getattr(self.server, "config_path", None)
            if isinstance(cfg_path, Path) and cfg_path.exists():
                try:
                    fresh = load_config(cfg_path)
                    valid_pins = {str(fresh.get("pin", "")).strip()}
                except Exception:
                    pass
            pin_matches = any(secrets.compare_digest(received_pin.encode("utf-8"), vp.encode("utf-8")) for vp in valid_pins if vp)
            if not pin_matches:
                with SESSIONS_LOCK:
                    if len(LOGIN_FAILURES) > 2048:
                        LOGIN_FAILURES.clear()
                    LOGIN_FAILURES[address] = failures + [time.time()]
                self.send_bytes(403, login_page("Wrong PIN."))
                return

            self._record_client_seen("/login")
            token = secrets.token_urlsafe(32)
            with SESSIONS_LOCK:
                expired = [key for key, at in SESSIONS.items() if at < time.time()]
                for key in expired:
                    SESSIONS.pop(key, None)
                if len(SESSIONS) >= 512:
                    SESSIONS.pop(next(iter(SESSIONS)))
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
                command = payload.get("command") if isinstance(payload, dict) else None
            except (json.JSONDecodeError, UnicodeDecodeError):
                command = None

            if not isinstance(command, str) or command not in COMMANDS:
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
    parser.add_argument("--https", action="store_true", help="Enable local self-signed HTTPS")
    return parser.parse_args()


def main() -> int:
    single_instance_mutex = None
    linux_lock_fh = None
    if os.name == "nt":
        # Ensure single-instance using a Named Mutex on Windows
        single_instance_mutex = ctypes.windll.kernel32.CreateMutexW(None, True, r"Global\PCPhoneRemoteAppPySingleInstanceMutex")
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            print("Another instance of PC Phone Remote is already running. Exiting.")
            return 0
    else:
        try:
            import fcntl
            lock_path = Path("/tmp/pc_phone_remote_server.lock")
            linux_lock_fh = lock_path.open("w")
            fcntl.flock(linux_lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:
            pass
        except OSError:
            print("Another instance of PC Phone Remote is already running. Exiting.")
            return 0

    try:
        from brand_icon import ensure_brand_assets
        ensure_brand_assets()
    except Exception:
        pass

    args = parse_args()
    cfg_file = Path(__file__).with_name("config.json")
    config = load_config(cfg_file)
    server = ThreadingHTTPServer((args.host, args.port), RemoteHandler)
    server.https_enabled = False  # type: ignore[attr-defined]
    use_https = bool(args.https or config.get("https_enabled"))
    if use_https:
        try:
            cert_p, key_p = ensure_local_tls_cert(ordered_lan_ips(args.port))
            wrap_server_ssl(server, cert_p, key_p)
            server.https_enabled = True  # type: ignore[attr-defined]
        except Exception as exc:
            print(f"WARNING: Could not enable HTTPS ({exc}); falling back to HTTP.")
    server.pin = args.pin or str(config.get("pin", ""))  # type: ignore[attr-defined]
    if not args.pin:
        server.config_path = cfg_file  # type: ignore[attr-defined]
    server.companion = Companion(config, run_command)
    start_udp_discovery_listener(args.port, https_enabled=bool(server.https_enabled))

    scheme = "https" if server.https_enabled else "http"
    print(f"{APP_NAME} v{APP_VERSION} is running ({'Windows' if os.name == 'nt' else 'Linux'}, {scheme.upper()}).")
    if server.pin:
        print("PIN is configured.")
    else:
        print("WARNING: no PIN is configured. Set REMOTE_PIN before real use.")
    print("Open one of these addresses on your phone (or iPhone Safari /app) while connected to the same Wi-Fi:")
    for address in local_addresses(args.port):
        print(f"  {address.replace('http://', scheme + '://')}/app")
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
