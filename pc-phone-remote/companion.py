"""Shared, allowlisted features used by both the LAN server and relay agent."""
from __future__ import annotations

import base64
import binascii
import ctypes
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

from unlock_ipc import DEFAULT_CONTROL_PIPE, pipe_transact

APP_DIR = Path(__file__).resolve().parent
MAX_FILE = 8 * 1024 * 1024
MAX_BODY = 12 * 1024 * 1024
ACTIONS = {
    "status",
    "files.list",
    "files.put",
    "files.get",
    "files.open_folder",
    "note.get",
    "note.set",
    "media",
    "timer.set",
    "timer.cancel",
    "command",
    "unlock.status",
    "unlock.enroll",
    "unlock.challenge",
    "unlock.submit",
    "touchpad",
    "scenes.run",
    "deck.run",
    "wol.wake",
    "processes.list",
}


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_str(cls, text: str) -> "_GUID":
        u = uuid.UUID(text)
        d1, d2, d3 = u.fields[:3]
        return cls(d1, d2, d3, (ctypes.c_ubyte * 8)(*u.bytes[8:]))


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _vtable_func(obj_ptr: ctypes.c_void_p, slot: int, restype, *argtypes):
    vtbl = ctypes.cast(obj_ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn_type = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return fn_type(vtbl[slot])


def control_windows_audio(action: str) -> dict | None:
    """Directly controls the Windows CoreAudio master endpoint (IAudioEndpointVolume) via COM."""
    if os.name != "nt":
        return None
    clsid_enum = _GUID.from_str("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
    iid_enum = _GUID.from_str("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
    iid_ep = _GUID.from_str("{5CDF2C82-841E-4546-9722-0CF74078229A}")

    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx(None, 0)
    enum_ptr = ctypes.c_void_p()
    dev_ptr = ctypes.c_void_p()
    ep_ptr = ctypes.c_void_p()
    try:
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid_enum),
            None,
            23,
            ctypes.byref(iid_enum),
            ctypes.byref(enum_ptr),
        )
        if hr != 0 or not enum_ptr.value:
            return None
        get_default = _vtable_func(
            enum_ptr, 4, ctypes.c_long, ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)
        )
        if get_default(enum_ptr, 0, 1, ctypes.byref(dev_ptr)) != 0 or not dev_ptr.value:
            return None
        activate = _vtable_func(
            dev_ptr, 3, ctypes.c_long, ctypes.POINTER(_GUID), ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
        )
        if activate(dev_ptr, ctypes.byref(iid_ep), 23, None, ctypes.byref(ep_ptr)) != 0 or not ep_ptr.value:
            return None

        get_vol = _vtable_func(ep_ptr, 9, ctypes.c_long, ctypes.POINTER(ctypes.c_float))
        set_vol = _vtable_func(ep_ptr, 7, ctypes.c_long, ctypes.c_float, ctypes.c_void_p)
        get_mute = _vtable_func(ep_ptr, 15, ctypes.c_long, ctypes.POINTER(ctypes.c_int))
        set_mute = _vtable_func(ep_ptr, 14, ctypes.c_long, ctypes.c_int, ctypes.c_void_p)

        cur_vol = ctypes.c_float(0.0)
        cur_mute = ctypes.c_int(0)
        get_vol(ep_ptr, ctypes.byref(cur_vol))
        get_mute(ep_ptr, ctypes.byref(cur_mute))

        if action == "mute":
            new_mute = 0 if cur_mute.value else 1
            set_mute(ep_ptr, new_mute, None)
            cur_mute.value = new_mute
        elif action == "volume_up":
            if cur_mute.value:
                set_mute(ep_ptr, 0, None)
                cur_mute.value = 0
            new_v = min(1.0, max(0.0, float(cur_vol.value) + 0.06))
            set_vol(ep_ptr, ctypes.c_float(new_v), None)
            cur_vol.value = new_v
        elif action == "volume_down":
            new_v = min(1.0, max(0.0, float(cur_vol.value) - 0.06))
            set_vol(ep_ptr, ctypes.c_float(new_v), None)
            cur_vol.value = new_v

        return {"volume": round(float(cur_vol.value) * 100), "muted": bool(cur_mute.value)}
    except Exception:
        return None
    finally:
        for ptr in (ep_ptr, dev_ptr, enum_ptr):
            if ptr and ptr.value:
                try:
                    rel = _vtable_func(ptr, 2, ctypes.c_ulong)
                    rel(ptr)
                except Exception:
                    pass


def run_on_input_desktop(fn) -> None:
    """Runs `fn` on a fresh thread attached to the interactive WinSta0\\Default input desktop."""
    if os.name != "nt":
        fn()
        return
    err_holder: list[Exception] = []

    def _worker() -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.OpenInputDesktop.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        user32.OpenInputDesktop.restype = ctypes.c_void_p
        user32.SetThreadDesktop.argtypes = [ctypes.c_void_p]
        user32.SetThreadDesktop.restype = ctypes.c_int
        user32.CloseDesktop.argtypes = [ctypes.c_void_p]
        user32.CloseDesktop.restype = ctypes.c_int
        h_desk = user32.OpenInputDesktop(0, 0, 0x10000000)
        try:
            if h_desk:
                user32.SetThreadDesktop(h_desk)
            fn()
        except Exception as exc:
            err_holder.append(exc)
        finally:
            if h_desk:
                user32.CloseDesktop(h_desk)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=4.0)
    if err_holder:
        raise err_holder[0]


def load_config(path: Path | None = None) -> dict:
    path = path or APP_DIR / "config.json"
    config = json.loads(path.read_text("utf-8")) if path.exists() else {}
    if not isinstance(config, dict):
        raise ValueError("config.json must be an object")
    if not config.get("pin") and not os.environ.get("REMOTE_PIN"):
        config["pin"] = str(secrets.randbelow(90000000) + 10000000)
        # Exclusive create prevents competing LAN/tray launches choosing different PINs.
        try:
            with path.open("x", encoding="utf-8") as output:
                json.dump(config, output, indent=2)
        except FileExistsError:
            existing = json.loads(path.read_text("utf-8"))
            if existing.get("pin"):
                config = existing
            else:
                raise ValueError("Set a non-empty pin in config.json or REMOTE_PIN")
    return config


def primary_mac_address() -> str:
    node = uuid.getnode()
    if (node >> 40) & 1:
        return ""
    return ":".join(f"{(node >> shift) & 0xFF:02X}" for shift in range(40, -1, -8))


def send_wol_magic_packet(mac: str, broadcast: str = "255.255.255.255", port: int = 9) -> None:
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", mac or "")
    if len(cleaned) != 12:
        raise FeatureError("Invalid MAC address for Wake-on-LAN", 400)
    hw = bytes.fromhex(cleaned)
    packet = b"\xff" * 6 + hw * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast or "255.255.255.255", int(port or 9)))


class FeatureError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class Companion:
    def __init__(self, config: dict | None = None, command_runner=None, unlock_pipe: str | None = None):
        self.config = config or {}
        self.root = Path(self.config.get("share_dir") or APP_DIR / "shared").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.command_runner = command_runner
        self.unlock_pipe = unlock_pipe or self.config.get("unlock_pipe") or DEFAULT_CONTROL_PIPE
        self.started = time.time()
        self._sync_downloads_mirror()

    def _sync_downloads_mirror(self) -> None:
        dl = self._downloads_mirror_dir()
        if dl is None:
            return
        try:
            for item in self.root.iterdir():
                if item.is_file() and not item.is_symlink() and item.name != "shared-note.txt" and not item.name.startswith("."):
                    dest = dl / item.name
                    if not dest.exists():
                        shutil.copy2(item, dest)
        except OSError:
            pass

    def file_path(self, name: object) -> Path:
        if not isinstance(name, str) or not name or len(name) > 180:
            raise FeatureError("Invalid filename")
        if name in {".", ".."} or name != name.strip() or name.endswith(".") or re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
            raise FeatureError("Invalid filename")
        if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}:
            raise FeatureError("Reserved filename")
        target = self.root / name
        if target.is_symlink() or target.resolve().parent != self.root:
            raise FeatureError("File is outside the shared folder", 403)
        return target

    def _call_unlock_service(self, req: dict, auto_start: bool = True) -> dict:
        resp = pipe_transact(req, pipe_name=self.unlock_pipe, auto_start=auto_start)
        if not isinstance(resp, dict):
            raise FeatureError("Unlock service did not return a valid object", 502)
        if not resp.get("ok"):
            status = resp.get("status", 403)
            if not isinstance(status, int) or not 400 <= status <= 599:
                status = 403
            raise FeatureError(resp.get("message") or resp.get("error") or "Unlock operation failed", status)
        return resp

    def unlock_status_snapshot(self, auto_start: bool = False) -> dict:
        resp = pipe_transact({"op": "unlock.status"}, pipe_name=self.unlock_pipe, timeout_ms=1500, auto_start=auto_start)
        if not isinstance(resp, dict) or not resp.get("ok"):
            return {
                "available": False,
                "enrolled": False,
                "provider_installed": False,
                "device_id": "",
                "device_name": "",
                "user_sid": "",
                "qualified_user": "",
                "vault_mode": "split_key",
                "pc_pub": "",
                "pc_pub_fp": "",
            }
        return {
            "available": True,
            "enrolled": bool(resp.get("enrolled")),
            "provider_installed": bool(resp.get("provider_installed")),
            "device_id": str(resp.get("device_id", "")),
            "device_name": str(resp.get("device_name", "")),
            "user_sid": str(resp.get("user_sid", "")),
            "qualified_user": str(resp.get("qualified_user", "")),
            "vault_mode": str(resp.get("vault_mode", "split_key")),
            "pc_pub": str(resp.get("pc_pub", "")),
            "pc_pub_fp": str(resp.get("pc_pub_fp", "")),
        }

    def _downloads_mirror_dir(self) -> Path | None:
        if self.config.get("share_dir"):
            return None
        try:
            dl = Path.home() / "Downloads" / "PCPhoneRemote"
            dl.mkdir(parents=True, exist_ok=True)
            return dl
        except OSError:
            return None

    def dispatch(self, payload: dict) -> dict:
        if not isinstance(payload, dict) or not isinstance(payload.get("action"), str) or payload["action"] not in ACTIONS:
            raise FeatureError("Unsupported action")
        action = payload["action"]
        if action == "status":
            return self.status()
        if action == "files.list":
            files = []
            for path in sorted(self.root.iterdir(), key=lambda p: p.name.casefold()):
                if len(files) >= 500:
                    break
                if path.is_file() and not path.is_symlink() and not path.name.startswith("."):
                    info = path.stat()
                    files.append({"name": path.name, "size": info.st_size, "modified": int(info.st_mtime)})
            dl = self._downloads_mirror_dir()
            return {
                "files": files,
                "max_file_bytes": MAX_FILE,
                "share_dir": str(self.root),
                "downloads_dir": str(dl) if dl else str(self.root),
            }
        if action == "files.put":
            target = self.file_path(payload.get("name"))
            encoded = payload.get("data")
            if not isinstance(encoded, str) or len(encoded) > (MAX_FILE + 2) // 3 * 4:
                raise FeatureError("File limit is 8 MiB", 413)
            try:
                data = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError):
                raise FeatureError("Invalid file encoding") from None
            if len(data) > MAX_FILE:
                raise FeatureError("File limit is 8 MiB", 413)
            with self.lock:
                if shutil.disk_usage(self.root).free < len(data) + 16 * 1024 * 1024:
                    raise FeatureError("Not enough disk space", 507)
                try:
                    with target.open("xb") as output:
                        output.write(data)
                except FileExistsError:
                    raise FeatureError("A file with this name already exists", 409) from None
                dl = self._downloads_mirror_dir()
                if dl is not None:
                    try:
                        (dl / target.name).write_bytes(data)
                    except OSError:
                        pass
            return {
                "name": target.name,
                "size": len(data),
                "share_dir": str(self.root),
                "downloads_dir": str(dl) if dl else str(self.root),
            }
        if action == "files.open_folder":
            if os.name != "nt":
                raise FeatureError("Opening folder requires Windows", 501)
            dl = self._downloads_mirror_dir()
            if dl is not None:
                for p in self.root.iterdir():
                    if p.is_file() and not p.is_symlink() and not p.name.startswith(".") and p.name != "shared-note.txt":
                        dest = dl / p.name
                        if not dest.exists():
                            try:
                                shutil.copy2(p, dest)
                            except OSError:
                                pass
            open_target = str(dl if dl is not None else self.root)
            run_on_input_desktop(lambda: subprocess.Popen(["explorer.exe", open_target]))
            return {"opened": True, "path": open_target}
        if action == "files.get":
            target = self.file_path(payload.get("name"))
            try:
                with target.open("rb") as source:
                    data = source.read(MAX_FILE + 1)
            except (FileNotFoundError, IsADirectoryError):
                raise FeatureError("File not found", 404) from None
            if len(data) > MAX_FILE:
                raise FeatureError("File limit is 8 MiB", 413)
            return {"name": target.name, "data": base64.b64encode(data).decode("ascii")}
        if action == "note.get":
            with self.lock:
                note = self.file_path("shared-note.txt")
                if note.exists() and note.stat().st_size > 65536:
                    raise FeatureError("Text limit is 64 KiB", 413)
                return {"text": note.read_text("utf-8") if note.exists() else ""}
        if action == "note.set":
            value = payload.get("text")
            if not isinstance(value, str) or len(value.encode("utf-8")) > 65536:
                raise FeatureError("Text limit is 64 KiB", 413)
            with self.lock:
                self.file_path("shared-note.txt").write_text(value, "utf-8")
            return {"saved": True}
        if action == "media":
            keys = {"mute": 0xAD, "volume_down": 0xAE, "volume_up": 0xAF,
                    "next": 0xB0, "previous": 0xB1, "play_pause": 0xB3}
            key = payload.get("key")
            if not isinstance(key, str) or key not in keys:
                raise FeatureError("Unknown media key")
            if os.name != "nt":
                raise FeatureError("Media controls require Windows", 501)
            if self.session_locked() is True:
                raise FeatureError("Media controls require an unlocked Windows session", 409)
            audio_state = None
            if key in {"mute", "volume_down", "volume_up"}:
                audio_state = control_windows_audio(key)
            vk = keys[key]
            # Only send keybd_event for non-volume keys OR when CoreAudio returned None (otherwise sending BOTH changes volume twice or un-toggles mute!).
            if audio_state is None:
                def _send_media() -> None:
                    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
                run_on_input_desktop(_send_media)
            res: dict = {"sent": True}
            if audio_state:
                res.update(audio_state)
            return res
        if action in {"timer.set", "timer.cancel"}:
            if os.name != "nt":
                raise FeatureError("Power timer requires Windows", 501)
            args = ["shutdown.exe", "/a"]
            if action == "timer.set":
                minutes = payload.get("minutes")
                if type(minutes) is not int or not 1 <= minutes <= 180:
                    raise FeatureError("Choose 1 to 180 minutes")
                # /t > 0 implies /f in Windows: the client explicitly confirms data loss.
                args = ["shutdown.exe", "/s", "/t", str(minutes * 60)]
            result = subprocess.run(args, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                raise FeatureError("Windows rejected the timer (already scheduled, none active, or insufficient rights)", 409)
            return {"scheduled": action == "timer.set", "minutes": payload.get("minutes")}
        if action == "command":
            if not isinstance(payload.get("command"), str) or payload["command"] not in {"mute", "lock", "sleep", "restart", "shutdown"}:
                raise FeatureError("Unknown command")
            if self.command_runner is None:
                raise FeatureError("Command runner unavailable", 503)
            self.command_runner(payload["command"])
            return {"sent": True}

        # ------------------------------------------------ Native Phone Windows Unlock
        if action == "unlock.status":
            return self.unlock_status_snapshot(auto_start=True)

        if action == "unlock.enroll":
            for field in ("enroll_token", "device_id", "phone_pub", "signature"):
                if not isinstance(payload.get(field), str) or not payload.get(field):
                    raise FeatureError(f"Missing {field}", 400)
            return self._call_unlock_service({
                "op": "enroll.complete",
                "enroll_token": payload["enroll_token"],
                "device_id": payload["device_id"],
                "device_name": str(payload.get("device_name") or "Android Phone")[:64],
                "phone_pub": payload["phone_pub"],
                "signature": payload["signature"],
            })

        if action == "unlock.challenge":
            return self._call_unlock_service({"op": "unlock.challenge"})

        if action == "unlock.submit":
            required = ("challenge_id", "device_id", "user_sid", "timestamp", "eph_pub", "iv", "ciphertext", "signature")
            for field in required:
                if field not in payload:
                    raise FeatureError(f"Missing {field}", 400)
            req = {
                "op": "unlock.submit",
                "challenge_id": str(payload["challenge_id"]),
                "device_id": str(payload["device_id"]),
                "user_sid": str(payload["user_sid"]),
                "timestamp": str(payload["timestamp"]),
                "eph_pub": str(payload["eph_pub"]),
                "iv": str(payload["iv"]),
                "ciphertext": str(payload["ciphertext"]),
                "signature": str(payload["signature"]),
            }
            return self._call_unlock_service(req)

        # ------------------------------------------------ Commercial / Pro Features
        if action == "touchpad":
            return self._handle_touchpad(payload)
        if action == "scenes.run":
            return self._handle_scene(payload)
        if action == "deck.run":
            return self._handle_deck(payload)
        if action == "wol.wake":
            mac = payload.get("mac") or self.config.get("mac") or primary_mac_address()
            if not isinstance(mac, str) or not mac:
                raise FeatureError("MAC address is required for Wake-on-LAN", 400)
            send_wol_magic_packet(mac, str(payload.get("broadcast") or "255.255.255.255"))
            return {"sent": True, "mac": mac}
        if action == "processes.list":
            if not psutil:
                return {"processes": []}
            procs = []
            for p in psutil.process_iter(["pid", "name", "memory_percent", "memory_info"]):
                try:
                    info = p.info
                    mem_info = info.get("memory_info")
                    mem_mb = round((mem_info.rss / (1024 * 1024)) if mem_info else 0.0, 1)
                    procs.append({
                        "pid": info["pid"],
                        "name": str(info.get("name") or "")[:48],
                        "ram": round(float(info.get("memory_percent") or 0.0), 1),
                        "mem_mb": mem_mb,
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            procs.sort(key=lambda item: item["mem_mb"], reverse=True)
            return {"processes": procs[:15]}

        raise FeatureError("Unsupported action")

    def _handle_touchpad(self, payload: dict) -> dict:
        if os.name != "nt":
            raise FeatureError("Touchpad requires Windows", 501)
        if self.session_locked() is True:
            raise FeatureError("Touchpad requires an unlocked Windows session", 409)
        kind = payload.get("type") or payload.get("mode")
        if kind == "move":
            dx = max(-400, min(400, int(payload.get("dx", 0))))
            dy = max(-400, min(400, int(payload.get("dy", 0))))
            def _do_move() -> None:
                user32 = ctypes.windll.user32
                pt = _POINT()
                if user32.GetCursorPos(ctypes.byref(pt)):
                    user32.SetCursorPos(pt.x + dx, pt.y + dy)
                user32.mouse_event(0x0001, dx, dy, 0, 0)
            run_on_input_desktop(_do_move)
            return {"sent": True}
        if kind == "click":
            btn = payload.get("button", "left")
            def _do_click() -> None:
                user32 = ctypes.windll.user32
                if btn == "right":
                    user32.mouse_event(0x0008, 0, 0, 0, 0)
                    user32.mouse_event(0x0010, 0, 0, 0, 0)
                elif btn == "double":
                    for _ in range(2):
                        user32.mouse_event(0x0002, 0, 0, 0, 0)
                        user32.mouse_event(0x0004, 0, 0, 0, 0)
                else:
                    user32.mouse_event(0x0002, 0, 0, 0, 0)
                    user32.mouse_event(0x0004, 0, 0, 0, 0)
            run_on_input_desktop(_do_click)
            return {"sent": True}
        if kind == "scroll":
            raw_delta = payload.get("delta")
            if raw_delta is not None:
                delta = max(-1200, min(1200, int(raw_delta)))
            else:
                delta = max(-1200, min(1200, int(payload.get("dy", 0)) * 120))
            run_on_input_desktop(lambda: ctypes.windll.user32.mouse_event(0x0800, 0, 0, delta, 0))
            return {"sent": True}
        if kind == "key":
            vk_map = {
                "space": 0x20, "enter": 0x0D, "backspace": 0x08,
                "escape": 0x1B, "esc": 0x1B,
                "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
                "page_up": 0x21, "page_down": 0x22, "f5": 0x74,
            }
            key = payload.get("key")
            if key not in vk_map:
                raise FeatureError("Unsupported key", 400)
            vk = vk_map[key]
            def _do_key() -> None:
                user32 = ctypes.windll.user32
                user32.keybd_event(vk, 0, 0, 0)
                user32.keybd_event(vk, 0, 2, 0)
            run_on_input_desktop(_do_key)
            return {"sent": True}
        raise FeatureError("Unsupported touchpad event", 400)

    def _handle_scene(self, payload: dict) -> dict:
        scene = payload.get("scene")
        if scene not in {"movie", "night", "away", "work", "presentation"}:
            raise FeatureError("Unknown scene", 400)
        if scene == "away":
            if self.command_runner:
                self.command_runner("lock")
            return {"sent": True, "scene": scene}
        if os.name == "nt" and self.session_locked() is not True:
            if scene == "movie":
                for _ in range(3):
                    control_windows_audio("volume_down")
                def _play() -> None:
                    ctypes.windll.user32.keybd_event(0xB3, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(0xB3, 0, 2, 0)
                run_on_input_desktop(_play)
            elif scene == "night":
                control_windows_audio("mute")
                subprocess.run(["shutdown.exe", "/s", "/t", "3600"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            elif scene == "work":
                subprocess.run(["shutdown.exe", "/a"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            elif scene == "presentation":
                def _f5() -> None:
                    ctypes.windll.user32.keybd_event(0x74, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(0x74, 0, 2, 0)
                run_on_input_desktop(_f5)
        return {"sent": True, "scene": scene}

    def _handle_deck(self, payload: dict) -> dict:
        macro = payload.get("macro")
        allowed = {"desktop", "task_manager", "explorer", "lock", "mute", "play_pause", "screenshot", "browser"}
        if macro not in allowed:
            raise FeatureError("Unknown Stream Deck macro", 400)
        if macro == "lock" and self.command_runner:
            self.command_runner("lock")
            return {"sent": True, "macro": macro}
        if os.name != "nt" or self.session_locked() is True:
            raise FeatureError("Macro requires an unlocked Windows session", 409)
        if macro == "mute":
            if control_windows_audio("mute") is None:
                def _mute_vk() -> None:
                    ctypes.windll.user32.keybd_event(0xAD, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(0xAD, 0, 2, 0)
                run_on_input_desktop(_mute_vk)
            return {"sent": True, "macro": macro}

        def _exec_macro() -> None:
            user32 = ctypes.windll.user32
            if macro == "desktop":
                # Win+D toggles Show Desktop directly in the interactive shell on WinSta0\Default.
                user32.keybd_event(0x5B, 0, 0, 0)
                user32.keybd_event(0x44, 0, 0, 0)
                user32.keybd_event(0x44, 0, 2, 0)
                user32.keybd_event(0x5B, 0, 2, 0)
            elif macro == "task_manager":
                # Ctrl+Shift+Esc invokes Task Manager natively via winlogon/explorer on WinSta0\Default.
                user32.keybd_event(0x11, 0, 0, 0)
                user32.keybd_event(0x10, 0, 0, 0)
                user32.keybd_event(0x1B, 0, 0, 0)
                user32.keybd_event(0x1B, 0, 2, 0)
                user32.keybd_event(0x10, 0, 2, 0)
                user32.keybd_event(0x11, 0, 2, 0)
            elif macro == "explorer":
                # Win+E opens File Explorer in the active interactive shell on WinSta0\Default.
                user32.keybd_event(0x5B, 0, 0, 0)
                user32.keybd_event(0x45, 0, 0, 0)
                user32.keybd_event(0x45, 0, 2, 0)
                user32.keybd_event(0x5B, 0, 2, 0)
            elif macro == "browser":
                # VK_BROWSER_HOME (0xAC) opens the default browser on WinSta0\Default.
                user32.keybd_event(0xAC, 0, 0, 0)
                user32.keybd_event(0xAC, 0, 2, 0)
            elif macro == "play_pause":
                user32.keybd_event(0xB3, 0, 0, 0)
                user32.keybd_event(0xB3, 0, 2, 0)
            elif macro == "screenshot":
                # Win+PrintScreen flashes the display and saves to Pictures\Screenshots + Clipboard.
                user32.keybd_event(0x5B, 0, 0, 0)
                user32.keybd_event(0x2C, 0, 0, 0)
                user32.keybd_event(0x2C, 0, 2, 0)
                user32.keybd_event(0x5B, 0, 2, 0)
                try:
                    from PIL import ImageGrab
                    img = ImageGrab.grab()
                    fname = f"Screenshot_PC_{int(time.time())}.png"
                    img.save(self.root / fname, "PNG")
                    dl = self._downloads_mirror_dir()
                    if dl is not None:
                        img.save(dl / fname, "PNG")
                except Exception:
                    pass

        run_on_input_desktop(_exec_macro)
        return {"sent": True, "macro": macro}

    @staticmethod
    def session_locked():
        if os.name != "nt":
            return None
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.OpenInputDesktop.restype = ctypes.c_void_p
        user32.SwitchDesktop.argtypes = [ctypes.c_void_p]
        user32.CloseDesktop.argtypes = [ctypes.c_void_p]
        desktop = user32.OpenInputDesktop(0, False, 0x100)
        if not desktop:
            return True
        try:
            return not bool(user32.SwitchDesktop(desktop))
        finally:
            user32.CloseDesktop(desktop)

    def status(self):
        config_path = APP_DIR / "config.json"
        if config_path.exists():
            try:
                updated = json.loads(config_path.read_text("utf-8"))
                if isinstance(updated.get("rdp"), dict):
                    self.config["rdp"] = updated["rdp"]
            except (OSError, ValueError):
                pass
        dl = self._downloads_mirror_dir()
        result = {
            "hostname": socket.gethostname(),
            "api_version": 3,
            "locked": self.session_locked(),
            "max_file_bytes": MAX_FILE,
            "share_dir": str(self.root),
            "downloads_dir": str(dl) if dl else str(self.root),
            "mac": self.config.get("mac") or primary_mac_address(),
            "rdp": {key: self.config.get("rdp", {}).get(key, "") for key in ("host", "username", "gateway")},
            "unlock": self.unlock_status_snapshot(auto_start=True),
            "metrics_available": psutil is not None,
        }
        result["rdp"]["port"] = self.config.get("rdp", {}).get("port", 3389)
        if psutil:
            result.update(
                cpu=psutil.cpu_percent(interval=0.15),
                ram=psutil.virtual_memory().percent,
                disk_free=shutil.disk_usage(self.root).free,
                uptime=int(time.time() - psutil.boot_time()),
            )
            battery = psutil.sensors_battery()
            result["battery"] = round(battery.percent) if battery else None
        return result
