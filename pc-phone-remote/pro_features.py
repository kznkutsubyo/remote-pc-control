"""Advanced PC remote features: Screen capture/tap, Unicode keyboard/hotkeys,
OS clipboard sync, CoreAudio/PulseAudio output switcher & app mixer, display
brightness/off, safe process termination, custom Studio Pro buttons, WoL
diagnostics/autofix, and GitHub Releases update checker.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import io
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

APP_VERSION = "2.4.0"
GITHUB_REPO = "kznkutsubyo/remote-pc-control"
MAX_CLIPBOARD_BYTES = 65536
MAX_TYPE_CHARS = 2000

PROTECTED_PROCESS_NAMES = {
    "system",
    "system idle process",
    "registry",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "winlogon.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
    "dwm.exe",
    "fontdrvhost.exe",
    "memory compression",
    "systemd",
    "init",
    "kthreadd",
    "dbus-daemon",
}

HOTKEYS: dict[str, tuple[list[int], str]] = {
    "alt_tab": ([0x12, 0x09], "alt+Tab"),
    "win_d": ([0x5B, 0x44], "super+d"),
    "win_e": ([0x5B, 0x45], "super+e"),
    "win_l": ([0x5B, 0x4C], "super+l"),
    "alt_f4": ([0x12, 0x73], "alt+F4"),
    "ctrl_shift_esc": ([0x11, 0x10, 0x1B], "ctrl+shift+Escape"),
    "ctrl_c": ([0x11, 0x43], "ctrl+c"),
    "ctrl_v": ([0x11, 0x56], "ctrl+v"),
    "ctrl_x": ([0x11, 0x58], "ctrl+x"),
    "ctrl_z": ([0x11, 0x5A], "ctrl+z"),
    "ctrl_a": ([0x11, 0x41], "ctrl+a"),
    "ctrl_s": ([0x11, 0x53], "ctrl+s"),
    "ctrl_w": ([0x11, 0x57], "ctrl+w"),
    "ctrl_t": ([0x11, 0x54], "ctrl+t"),
    "ctrl_tab": ([0x11, 0x09], "ctrl+Tab"),
    "switch_lang": ([0x12, 0x10], "alt+Shift_L"),
    "enter": ([0x0D], "Return"),
    "backspace": ([0x08], "BackSpace"),
    "tab": ([0x09], "Tab"),
    "esc": ([0x1B], "Escape"),
    "f5": ([0x74], "F5"),
    "f11": ([0x7A], "F11"),
    "print_screen": ([0x2C], "Print"),
}


# ---------------------------------------------------------------------------
# COM helpers (Windows CoreAudio / PolicyConfig)
# ---------------------------------------------------------------------------
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


class _PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", ctypes.c_uint32)]


class _PROPVARIANT(ctypes.Structure):
    _fields_ = [
        ("vt", ctypes.c_uint16),
        ("wReserved1", ctypes.c_uint16),
        ("wReserved2", ctypes.c_uint16),
        ("wReserved3", ctypes.c_uint16),
        ("val", ctypes.c_void_p),
        ("pad", ctypes.c_void_p),
    ]


def _vtable_func(obj_ptr: ctypes.c_void_p, slot: int, restype, *argtypes):
    vtbl = ctypes.cast(obj_ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn_type = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return fn_type(vtbl[slot])


def _com_release(ptr: ctypes.c_void_p | None) -> None:
    if ptr and ptr.value:
        try:
            _vtable_func(ptr, 2, ctypes.c_ulong)(ptr)
        except Exception:
            pass


def _ole32():
    dll = ctypes.windll.ole32
    dll.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    dll.CoInitializeEx.restype = ctypes.c_long
    dll.CoCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
    dll.CoCreateInstance.restype = ctypes.c_long
    dll.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    dll.CoTaskMemFree.restype = None
    return dll


# ---------------------------------------------------------------------------
# 1. Screen Capture & Coordinate Tap
# ---------------------------------------------------------------------------
def list_monitors() -> list[dict]:
    """Return physical display rectangles for monitor selection."""
    if os.name == "nt":
        monitors: list[dict] = []
        user32 = ctypes.windll.user32

        class _RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_RECT), ctypes.c_ssize_t
        )
        user32.EnumDisplayMonitors.argtypes = [ctypes.c_void_p, ctypes.c_void_p, MonitorEnumProc, ctypes.c_ssize_t]
        user32.EnumDisplayMonitors.restype = ctypes.c_int

        def _cb(hmon, hdc, lprect, lparam):
            r = lprect.contents
            idx = len(monitors)
            monitors.append({
                "id": idx,
                "name": f"Monitor {idx + 1}",
                "left": int(r.left),
                "top": int(r.top),
                "right": int(r.right),
                "bottom": int(r.bottom),
                "width": max(1, int(r.right - r.left)),
                "height": max(1, int(r.bottom - r.top)),
            })
            return 1

        try:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
            user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_cb), 0)
        except Exception:
            pass
        if monitors:
            return monitors
        w = int(user32.GetSystemMetrics(0) or 1920)
        h = int(user32.GetSystemMetrics(1) or 1080)
        return [{"id": 0, "name": "Monitor 1", "left": 0, "top": 0, "right": w, "bottom": h, "width": w, "height": h}]

    w, h = 1920, 1080
    if shutil.which("xrandr"):
        try:
            out = subprocess.run(["xrandr", "--current"], capture_output=True, text=True, timeout=2).stdout
            m = re.search(r"current\s+(\d+)\s*x\s*(\d+)", out)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
        except Exception:
            pass
    return [{"id": 0, "name": "Display 1", "left": 0, "top": 0, "right": w, "bottom": h, "width": w, "height": h}]


def capture_screen_jpeg(monitor_idx: int = 0, max_width: int = 960, quality: int = 60) -> tuple[bytes, int, int, list[dict]]:
    """Capture the requested monitor as a resized JPEG byte stream."""
    from PIL import Image, ImageGrab

    monitors = list_monitors()
    idx = max(0, min(int(monitor_idx or 0), len(monitors) - 1))
    mon = monitors[idx]
    max_w = max(240, min(1920, int(max_width or 960)))
    qual = max(25, min(90, int(quality or 60)))

    img = None
    if os.name == "nt":
        bbox = (mon["left"], mon["top"], mon["right"], mon["bottom"])
        try:
            img = ImageGrab.grab(bbox=bbox, all_screens=True)
        except Exception:
            img = ImageGrab.grab()
    else:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tmp_path = Path(tf.name)
        try:
            for cmd in (
                ["grim", str(tmp_path)],
                ["scrot", "-o", str(tmp_path)],
                ["gnome-screenshot", "-f", str(tmp_path)],
                ["spectacle", "-b", "-n", "-o", str(tmp_path)],
            ):
                if shutil.which(cmd[0]):
                    res = subprocess.run(cmd, capture_output=True, timeout=5)
                    if res.returncode == 0 and tmp_path.exists() and tmp_path.stat().st_size > 0:
                        img = Image.open(tmp_path).convert("RGB")
                        break
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
        if img is None:
            raise RuntimeError("Install grim, scrot, gnome-screenshot, or spectacle for Linux screen capture")

    if img.mode != "RGB":
        img = img.convert("RGB")
    if img.width > max_w:
        ratio = max_w / float(img.width)
        resample = Image.Resampling.BILINEAR if hasattr(Image, "Resampling") else Image.BILINEAR
        img = img.resize((max_w, max(1, int(img.height * ratio))), resample)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=qual, optimize=True)
    return buf.getvalue(), img.width, img.height, [
        {"id": m["id"], "name": m["name"], "width": m["width"], "height": m["height"]} for m in monitors
    ]


def tap_screen(nx: float, ny: float, monitor_idx: int = 0, button: str = "left", run_desktop_fn=None) -> dict:
    """Click at normalized (nx, ny) coordinates in [0.0, 1.0] on the given monitor."""
    nx_c = max(0.0, min(1.0, float(nx)))
    ny_c = max(0.0, min(1.0, float(ny)))
    monitors = list_monitors()
    idx = max(0, min(int(monitor_idx or 0), len(monitors) - 1))
    mon = monitors[idx]
    abs_x = int(mon["left"] + nx_c * max(1, mon["width"] - 1))
    abs_y = int(mon["top"] + ny_c * max(1, mon["height"] - 1))
    btn = button if button in {"left", "right", "double"} else "left"

    if os.name == "nt":
        def _do() -> None:
            user32 = ctypes.windll.user32
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
            user32.SetCursorPos(abs_x, abs_y)
            time.sleep(0.02)
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
        if run_desktop_fn:
            run_desktop_fn(_do)
        else:
            _do()
    else:
        if shutil.which("xdotool"):
            subprocess.run(["xdotool", "mousemove", "--", str(abs_x), str(abs_y)], capture_output=True, check=False)
            if btn == "right":
                subprocess.run(["xdotool", "click", "3"], capture_output=True, check=False)
            elif btn == "double":
                subprocess.run(["xdotool", "click", "--repeat", "2", "1"], capture_output=True, check=False)
            else:
                subprocess.run(["xdotool", "click", "1"], capture_output=True, check=False)
        else:
            raise RuntimeError("Install xdotool for Linux screen tap support")

    return {"sent": True, "x": abs_x, "y": abs_y, "button": btn, "monitor": idx}


# ---------------------------------------------------------------------------
# 2. Live Unicode Keyboard & Allowlisted Hotkeys
# ---------------------------------------------------------------------------
def type_unicode_text(text: str, run_desktop_fn=None) -> dict:
    """Type arbitrary Unicode text (Cyrillic, Latin, symbols) into the focused window."""
    if not isinstance(text, str) or not text:
        raise ValueError("Text is required")
    if len(text) > MAX_TYPE_CHARS:
        raise ValueError(f"Text exceeds {MAX_TYPE_CHARS} characters")

    if os.name == "nt":
        class _KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class _MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class _INPUTUNION(ctypes.Union):
            _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]

        class _INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

        INPUT_KEYBOARD = 1
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_UNICODE = 0x0004

        def _send() -> None:
            user32 = ctypes.windll.user32
            user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
            user32.SendInput.restype = wintypes.UINT
            events: list[_INPUT] = []
            for ch in text:
                if ch == "\r":
                    continue
                if ch == "\n":
                    for fl in (0, KEYEVENTF_KEYUP):
                        inp = _INPUT(type=INPUT_KEYBOARD)
                        inp.u.ki.wVk = 0x0D
                        inp.u.ki.dwFlags = fl
                        events.append(inp)
                    continue
                utf16 = ch.encode("utf-16-le")
                for i in range(0, len(utf16), 2):
                    code_unit = int.from_bytes(utf16[i:i + 2], "little")
                    for fl in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
                        inp = _INPUT(type=INPUT_KEYBOARD)
                        inp.u.ki.wVk = 0
                        inp.u.ki.wScan = code_unit
                        inp.u.ki.dwFlags = fl
                        events.append(inp)
            if events:
                arr = (_INPUT * len(events))(*events)
                user32.SendInput(len(events), ctypes.byref(arr), ctypes.sizeof(_INPUT))

        if run_desktop_fn:
            run_desktop_fn(_send)
        else:
            _send()
        return {"sent": True, "length": len(text)}

    if shutil.which("wtype"):
        subprocess.run(["wtype", "--", text], capture_output=True, check=True, timeout=5)
    elif shutil.which("xdotool"):
        subprocess.run(["xdotool", "type", "--clearmodifiers", "--delay", "10", "--", text], capture_output=True, check=True, timeout=8)
    else:
        raise RuntimeError("Install wtype or xdotool for Linux text typing")
    return {"sent": True, "length": len(text)}


def send_hotkey(hotkey: str, run_desktop_fn=None) -> dict:
    """Send an allowlisted keyboard shortcut to the focused PC desktop."""
    if not isinstance(hotkey, str) or hotkey not in HOTKEYS:
        raise ValueError(f"Unsupported hotkey: {hotkey}")
    vk_seq, linux_combo = HOTKEYS[hotkey]
    if os.name == "nt":
        def _send() -> None:
            user32 = ctypes.windll.user32
            for vk in vk_seq:
                user32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.025)
            for vk in reversed(vk_seq):
                user32.keybd_event(vk, 0, 2, 0)
        if run_desktop_fn:
            run_desktop_fn(_send)
        else:
            _send()
        return {"sent": True, "hotkey": hotkey}

    if shutil.which("xdotool"):
        subprocess.run(["xdotool", "key", "--clearmodifiers", linux_combo], capture_output=True, check=False, timeout=4)
        return {"sent": True, "hotkey": hotkey}
    raise RuntimeError("Install xdotool for Linux hotkeys")


# ---------------------------------------------------------------------------
# 3. Real OS Clipboard Sync
# ---------------------------------------------------------------------------
def get_clipboard_text() -> str:
    """Read current Unicode text from the OS clipboard."""
    if os.name == "nt":
        CF_UNICODETEXT = 13
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.restype = ctypes.c_int
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = ctypes.c_int
        user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
        user32.IsClipboardFormatAvailable.restype = ctypes.c_int
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.restype = ctypes.c_int

        for _ in range(5):
            if user32.OpenClipboard(None):
                try:
                    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                        return ""
                    handle = user32.GetClipboardData(CF_UNICODETEXT)
                    if not handle:
                        return ""
                    ptr = kernel32.GlobalLock(handle)
                    if not ptr:
                        return ""
                    try:
                        text = ctypes.wstring_at(ptr)
                        encoded = text.encode("utf-8")
                        if len(encoded) > MAX_CLIPBOARD_BYTES:
                            text = encoded[:MAX_CLIPBOARD_BYTES].decode("utf-8", errors="ignore")
                        return text
                    finally:
                        kernel32.GlobalUnlock(handle)
                finally:
                    user32.CloseClipboard()
            time.sleep(0.04)
        return ""

    for cmd in (["wl-paste", "--no-newline"], ["xclip", "-o", "-selection", "clipboard"], ["xsel", "-ob"]):
        if shutil.which(cmd[0]):
            res = subprocess.run(cmd, capture_output=True, timeout=3)
            if res.returncode == 0:
                return res.stdout[:MAX_CLIPBOARD_BYTES].decode("utf-8", errors="replace")
    return ""


def set_clipboard_text(text: str) -> dict:
    """Write Unicode text directly to the OS clipboard."""
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_CLIPBOARD_BYTES:
        raise ValueError("Clipboard text limit is 64 KiB")

    if os.name == "nt":
        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.restype = ctypes.c_int
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = ctypes.c_int
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = ctypes.c_int
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.restype = ctypes.c_int
        user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
        user32.SetClipboardData.restype = ctypes.c_void_p

        raw = (text + "\0").encode("utf-16-le")
        for _ in range(5):
            if user32.OpenClipboard(None):
                try:
                    user32.EmptyClipboard()
                    hmem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(raw))
                    if not hmem:
                        raise RuntimeError("GlobalAlloc failed")
                    ptr = kernel32.GlobalLock(hmem)
                    ctypes.memmove(ptr, raw, len(raw))
                    kernel32.GlobalUnlock(hmem)
                    if not user32.SetClipboardData(CF_UNICODETEXT, hmem):
                        raise RuntimeError("SetClipboardData failed")
                    return {"saved": True, "length": len(text)}
                finally:
                    user32.CloseClipboard()
            time.sleep(0.04)
        raise RuntimeError("Clipboard is busy")

    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "-ib"]):
        if shutil.which(cmd[0]):
            res = subprocess.run(cmd, input=text.encode("utf-8"), capture_output=True, timeout=3)
            if res.returncode == 0:
                return {"saved": True, "length": len(text)}
    raise RuntimeError("Install wl-clipboard, xclip, or xsel for Linux clipboard sync")


# ---------------------------------------------------------------------------
# 4. Audio Output Switcher & Per-App Volume Mixer
# ---------------------------------------------------------------------------
def _windows_audio_list() -> dict:
    clsid_enum = _GUID.from_str("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
    iid_enum = _GUID.from_str("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
    iid_session_mgr2 = _GUID.from_str("{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}")
    iid_session_ctl2 = _GUID.from_str("{bfb7ff88-7239-4fc9-8fa2-07c950be9c6d}")
    iid_simple_vol = _GUID.from_str("{87CE5498-68D6-44E5-9215-6DA47EF883D8}")
    pkey_friendly = _PROPERTYKEY(_GUID.from_str("{a45c254e-df1c-4efd-8020-67d146a850e0}"), 14)

    ole32 = _ole32()
    ole32.CoInitializeEx(None, 0)

    devices: list[dict] = []
    sessions: list[dict] = []
    enum_ptr = ctypes.c_void_p()
    coll_ptr = ctypes.c_void_p()
    def_dev_ptr = ctypes.c_void_p()
    default_id = ""

    try:
        if ole32.CoCreateInstance(ctypes.byref(clsid_enum), None, 23, ctypes.byref(iid_enum), ctypes.byref(enum_ptr)) != 0 or not enum_ptr.value:
            return {"devices": [], "sessions": []}

        get_def = _vtable_func(enum_ptr, 4, ctypes.c_long, ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))
        if get_def(enum_ptr, 0, 1, ctypes.byref(def_dev_ptr)) == 0 and def_dev_ptr.value:
            get_id = _vtable_func(def_dev_ptr, 5, ctypes.c_long, ctypes.POINTER(ctypes.c_void_p))
            id_ptr = ctypes.c_void_p()
            if get_id(def_dev_ptr, ctypes.byref(id_ptr)) == 0 and id_ptr.value:
                default_id = ctypes.wstring_at(id_ptr.value)
                ole32.CoTaskMemFree(id_ptr)

        enum_ep = _vtable_func(enum_ptr, 3, ctypes.c_long, ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))
        if enum_ep(enum_ptr, 0, 1, ctypes.byref(coll_ptr)) == 0 and coll_ptr.value:
            count = ctypes.c_uint(0)
            _vtable_func(coll_ptr, 3, ctypes.c_long, ctypes.POINTER(ctypes.c_uint))(coll_ptr, ctypes.byref(count))
            item_fn = _vtable_func(coll_ptr, 4, ctypes.c_long, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))
            for i in range(count.value):
                dev = ctypes.c_void_p()
                if item_fn(coll_ptr, i, ctypes.byref(dev)) != 0 or not dev.value:
                    continue
                try:
                    dev_id = ""
                    id_p = ctypes.c_void_p()
                    if _vtable_func(dev, 5, ctypes.c_long, ctypes.POINTER(ctypes.c_void_p))(dev, ctypes.byref(id_p)) == 0 and id_p.value:
                        dev_id = ctypes.wstring_at(id_p.value)
                        ole32.CoTaskMemFree(id_p)
                    name = dev_id
                    store = ctypes.c_void_p()
                    if _vtable_func(dev, 4, ctypes.c_long, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))(dev, 0, ctypes.byref(store)) == 0 and store.value:
                        try:
                            pv = _PROPVARIANT()
                            if _vtable_func(store, 5, ctypes.c_long, ctypes.POINTER(_PROPERTYKEY), ctypes.POINTER(_PROPVARIANT))(store, ctypes.byref(pkey_friendly), ctypes.byref(pv)) == 0:
                                if pv.vt == 31 and pv.val:
                                    name = ctypes.wstring_at(pv.val)
                                    ole32.CoTaskMemFree(pv.val)
                        finally:
                            _com_release(store)
                    if dev_id:
                        devices.append({"id": dev_id, "name": name[:80], "active": dev_id == default_id})
                finally:
                    _com_release(dev)

        if def_dev_ptr.value:
            mgr = ctypes.c_void_p()
            activate = _vtable_func(def_dev_ptr, 3, ctypes.c_long, ctypes.POINTER(_GUID), ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
            if activate(def_dev_ptr, ctypes.byref(iid_session_mgr2), 23, None, ctypes.byref(mgr)) == 0 and mgr.value:
                sess_enum = ctypes.c_void_p()
                try:
                    if _vtable_func(mgr, 5, ctypes.c_long, ctypes.POINTER(ctypes.c_void_p))(mgr, ctypes.byref(sess_enum)) == 0 and sess_enum.value:
                        scount = ctypes.c_int(0)
                        _vtable_func(sess_enum, 3, ctypes.c_long, ctypes.POINTER(ctypes.c_int))(sess_enum, ctypes.byref(scount))
                        get_sess = _vtable_func(sess_enum, 4, ctypes.c_long, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))
                        seen_pids: set[int] = set()
                        for i in range(scount.value):
                            ctl = ctypes.c_void_p()
                            if get_sess(sess_enum, i, ctypes.byref(ctl)) != 0 or not ctl.value:
                                continue
                            ctl2 = ctypes.c_void_p()
                            svol = ctypes.c_void_p()
                            try:
                                qi = _vtable_func(ctl, 0, ctypes.c_long, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))
                                if qi(ctl, ctypes.byref(iid_session_ctl2), ctypes.byref(ctl2)) != 0 or not ctl2.value:
                                    continue
                                if qi(ctl, ctypes.byref(iid_simple_vol), ctypes.byref(svol)) != 0 or not svol.value:
                                    continue
                                pid = ctypes.c_uint32(0)
                                _vtable_func(ctl2, 14, ctypes.c_long, ctypes.POINTER(ctypes.c_uint32))(ctl2, ctypes.byref(pid))
                                if pid.value == 0 or pid.value in seen_pids:
                                    continue
                                seen_pids.add(pid.value)
                                pname = f"PID {pid.value}"
                                if psutil:
                                    try:
                                        pname = psutil.Process(pid.value).name()
                                    except Exception:
                                        pass
                                vol = ctypes.c_float(1.0)
                                muted = ctypes.c_int(0)
                                _vtable_func(svol, 4, ctypes.c_long, ctypes.POINTER(ctypes.c_float))(svol, ctypes.byref(vol))
                                _vtable_func(svol, 6, ctypes.c_long, ctypes.POINTER(ctypes.c_int))(svol, ctypes.byref(muted))
                                sessions.append({
                                    "pid": int(pid.value),
                                    "name": pname[:48],
                                    "volume": round(float(vol.value) * 100),
                                    "muted": bool(muted.value),
                                })
                            finally:
                                _com_release(svol)
                                _com_release(ctl2)
                                _com_release(ctl)
                finally:
                    _com_release(sess_enum)
                    _com_release(mgr)
    finally:
        _com_release(coll_ptr)
        _com_release(def_dev_ptr)
        _com_release(enum_ptr)

    sessions.sort(key=lambda s: s["name"].casefold())
    return {"devices": devices, "sessions": sessions}


def _windows_set_audio_output(device_id: str) -> bool:
    clsid_policy = _GUID.from_str("{870af99c-171d-4f9e-af0d-e63df40c2bc9}")
    iids = [
        _GUID.from_str("{f8679f50-850a-41cf-9c72-430f290290c8}"),
        _GUID.from_str("{568b9108-44bf-40b4-9006-86afe5b5a620}"),
    ]
    ole32 = _ole32()
    ole32.CoInitializeEx(None, 0)
    for iid in iids:
        ptr = ctypes.c_void_p()
        if ole32.CoCreateInstance(ctypes.byref(clsid_policy), None, 23, ctypes.byref(iid), ctypes.byref(ptr)) == 0 and ptr.value:
            try:
                set_def = _vtable_func(ptr, 13, ctypes.c_long, ctypes.c_wchar_p, ctypes.c_int)
                ok = True
                for role in (0, 1, 2):
                    if set_def(ptr, device_id, role) != 0:
                        ok = False
                if ok:
                    return True
            finally:
                _com_release(ptr)
    return False


def _windows_set_app_volume(pid: int, volume: int | None = None, muted: bool | None = None) -> bool:
    clsid_enum = _GUID.from_str("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
    iid_enum = _GUID.from_str("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
    iid_session_mgr2 = _GUID.from_str("{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}")
    iid_session_ctl2 = _GUID.from_str("{bfb7ff88-7239-4fc9-8fa2-07c950be9c6d}")
    iid_simple_vol = _GUID.from_str("{87CE5498-68D6-44E5-9215-6DA47EF883D8}")

    ole32 = _ole32()
    ole32.CoInitializeEx(None, 0)
    enum_ptr = ctypes.c_void_p()
    def_dev_ptr = ctypes.c_void_p()
    mgr = ctypes.c_void_p()
    sess_enum = ctypes.c_void_p()
    updated = False
    try:
        if ole32.CoCreateInstance(ctypes.byref(clsid_enum), None, 23, ctypes.byref(iid_enum), ctypes.byref(enum_ptr)) != 0:
            return False
        if _vtable_func(enum_ptr, 4, ctypes.c_long, ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))(enum_ptr, 0, 1, ctypes.byref(def_dev_ptr)) != 0:
            return False
        if _vtable_func(def_dev_ptr, 3, ctypes.c_long, ctypes.POINTER(_GUID), ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(def_dev_ptr, ctypes.byref(iid_session_mgr2), 23, None, ctypes.byref(mgr)) != 0:
            return False
        if _vtable_func(mgr, 5, ctypes.c_long, ctypes.POINTER(ctypes.c_void_p))(mgr, ctypes.byref(sess_enum)) != 0:
            return False
        scount = ctypes.c_int(0)
        _vtable_func(sess_enum, 3, ctypes.c_long, ctypes.POINTER(ctypes.c_int))(sess_enum, ctypes.byref(scount))
        get_sess = _vtable_func(sess_enum, 4, ctypes.c_long, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))
        for i in range(scount.value):
            ctl = ctypes.c_void_p()
            if get_sess(sess_enum, i, ctypes.byref(ctl)) != 0 or not ctl.value:
                continue
            ctl2 = ctypes.c_void_p()
            svol = ctypes.c_void_p()
            try:
                qi = _vtable_func(ctl, 0, ctypes.c_long, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))
                if qi(ctl, ctypes.byref(iid_session_ctl2), ctypes.byref(ctl2)) != 0 or not ctl2.value:
                    continue
                if qi(ctl, ctypes.byref(iid_simple_vol), ctypes.byref(svol)) != 0 or not svol.value:
                    continue
                cur_pid = ctypes.c_uint32(0)
                _vtable_func(ctl2, 14, ctypes.c_long, ctypes.POINTER(ctypes.c_uint32))(ctl2, ctypes.byref(cur_pid))
                if int(cur_pid.value) == int(pid):
                    if volume is not None:
                        lvl = max(0.0, min(1.0, float(volume) / 100.0))
                        _vtable_func(svol, 3, ctypes.c_long, ctypes.c_float, ctypes.c_void_p)(svol, ctypes.c_float(lvl), None)
                    if muted is not None:
                        _vtable_func(svol, 5, ctypes.c_long, ctypes.c_int, ctypes.c_void_p)(svol, 1 if muted else 0, None)
                    updated = True
            finally:
                _com_release(svol)
                _com_release(ctl2)
                _com_release(ctl)
    finally:
        _com_release(sess_enum)
        _com_release(mgr)
        _com_release(def_dev_ptr)
        _com_release(enum_ptr)
    return updated


def list_audio_state() -> dict:
    """List playback audio output devices and active per-application volume sessions."""
    if os.name == "nt":
        return _windows_audio_list()

    devices: list[dict] = []
    sessions: list[dict] = []
    if shutil.which("pactl"):
        def_sink = subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True, timeout=3).stdout.strip()
        sinks_out = subprocess.run(["pactl", "list", "short", "sinks"], capture_output=True, text=True, timeout=3).stdout
        for line in sinks_out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                sid = parts[1].strip()
                devices.append({"id": sid, "name": sid[:80], "active": sid == def_sink})
        si_out = subprocess.run(["pactl", "list", "sink-inputs"], capture_output=True, text=True, timeout=3).stdout
        cur: dict | None = None
        for line in si_out.splitlines():
            m_idx = re.match(r"^Sink Input #(\d+)", line.strip())
            if m_idx:
                if cur:
                    sessions.append(cur)
                cur = {"pid": int(m_idx.group(1)), "name": f"Stream #{m_idx.group(1)}", "volume": 100, "muted": False}
            elif cur is not None:
                if "Mute:" in line:
                    cur["muted"] = "yes" in line.lower()
                elif "Volume:" in line:
                    mv = re.search(r"(\d+)%", line)
                    if mv:
                        cur["volume"] = min(150, int(mv.group(1)))
                elif "application.name =" in line:
                    mn = re.search(r'"([^"]+)"', line)
                    if mn:
                        cur["name"] = mn.group(1)[:48]
        if cur:
            sessions.append(cur)
    return {"devices": devices, "sessions": sessions}


def set_audio_output(device_id: str) -> dict:
    """Switch the default audio playback device."""
    if not isinstance(device_id, str) or not device_id.strip():
        raise ValueError("device_id is required")
    clean = device_id.strip()
    if os.name == "nt":
        if not _windows_set_audio_output(clean):
            raise RuntimeError("Could not switch Windows audio output device")
        return {"switched": True, "device_id": clean}
    if shutil.which("pactl"):
        res = subprocess.run(["pactl", "set-default-sink", clean], capture_output=True, timeout=3)
        if res.returncode == 0:
            return {"switched": True, "device_id": clean}
    if shutil.which("wpctl"):
        res = subprocess.run(["wpctl", "set-default", clean], capture_output=True, timeout=3)
        if res.returncode == 0:
            return {"switched": True, "device_id": clean}
    raise RuntimeError("Could not switch Linux audio output device")


def set_app_audio_volume(pid: int, volume: int | None = None, muted: bool | None = None) -> dict:
    """Set per-application volume (0..100) and/or mute state."""
    pid_i = int(pid)
    vol_i = None if volume is None else max(0, min(100, int(volume)))
    muted_b = None if muted is None else bool(muted)
    if os.name == "nt":
        ok = _windows_set_app_volume(pid_i, vol_i, muted_b)
        if not ok:
            raise RuntimeError(f"Audio session for PID {pid_i} not found")
        return {"updated": True, "pid": pid_i, "volume": vol_i, "muted": muted_b}
    if shutil.which("pactl"):
        if vol_i is not None:
            subprocess.run(["pactl", "set-sink-input-volume", str(pid_i), f"{vol_i}%"], capture_output=True, check=False, timeout=3)
        if muted_b is not None:
            subprocess.run(["pactl", "set-sink-input-mute", str(pid_i), "1" if muted_b else "0"], capture_output=True, check=False, timeout=3)
        return {"updated": True, "pid": pid_i, "volume": vol_i, "muted": muted_b}
    raise RuntimeError("Install pactl for Linux per-app audio mixer")


# ---------------------------------------------------------------------------
# 5. Display Brightness & Screen Off (without Sleep)
# ---------------------------------------------------------------------------
def _windows_ddc_brightness(new_level: int | None = None) -> int | None:
    """Query or set external monitor brightness via Windows dxva2 DDC/CI."""
    try:
        user32 = ctypes.windll.user32
        dxva2 = ctypes.windll.dxva2

        class _PHYSICAL_MONITOR(ctypes.Structure):
            _fields_ = [("hPhysicalMonitor", ctypes.c_void_p), ("szPhysicalMonitorDescription", ctypes.c_wchar * 128)]

        dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
        dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.restype = ctypes.c_int
        dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
        dxva2.GetPhysicalMonitorsFromHMONITOR.restype = ctypes.c_int
        dxva2.GetMonitorBrightness.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
        dxva2.GetMonitorBrightness.restype = ctypes.c_int
        dxva2.SetMonitorBrightness.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        dxva2.SetMonitorBrightness.restype = ctypes.c_int
        dxva2.DestroyPhysicalMonitors.argtypes = [wintypes.DWORD, ctypes.c_void_p]
        dxva2.DestroyPhysicalMonitors.restype = ctypes.c_int

        hmonitors: list[int] = []
        MonitorEnumProc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ssize_t)
        user32.EnumDisplayMonitors.argtypes = [ctypes.c_void_p, ctypes.c_void_p, MonitorEnumProc, ctypes.c_ssize_t]
        user32.EnumDisplayMonitors.restype = ctypes.c_int

        def _cb(hmon, hdc, lprect, lparam):
            if hmon:
                hmonitors.append(int(hmon))
            return 1

        user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_cb), 0)
        result_pct: int | None = None
        for hmon in hmonitors:
            cnt = wintypes.DWORD(0)
            if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(ctypes.c_void_p(hmon), ctypes.byref(cnt)) or cnt.value == 0:
                continue
            arr = (_PHYSICAL_MONITOR * cnt.value)()
            if not dxva2.GetPhysicalMonitorsFromHMONITOR(ctypes.c_void_p(hmon), cnt.value, ctypes.byref(arr)):
                continue
            try:
                for i in range(cnt.value):
                    hp = arr[i].hPhysicalMonitor
                    mn, cur, mx = wintypes.DWORD(0), wintypes.DWORD(0), wintypes.DWORD(100)
                    if dxva2.GetMonitorBrightness(hp, ctypes.byref(mn), ctypes.byref(cur), ctypes.byref(mx)):
                        span = max(1, mx.value - mn.value)
                        if new_level is not None:
                            target = int(mn.value + (max(0, min(100, new_level)) / 100.0) * span)
                            dxva2.SetMonitorBrightness(hp, target)
                            result_pct = max(0, min(100, new_level))
                        elif result_pct is None:
                            result_pct = round(((cur.value - mn.value) / float(span)) * 100.0)
            finally:
                dxva2.DestroyPhysicalMonitors(cnt.value, ctypes.byref(arr))
        return result_pct
    except Exception:
        return None


def get_display_brightness() -> dict:
    """Return current screen brightness (0..100) or supported=False if unavailable."""
    if os.name == "nt":
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty CurrentBrightness)"],
                capture_output=True, text=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            txt = res.stdout.strip()
            if txt.isdigit():
                return {"supported": True, "brightness": int(txt), "method": "wmi"}
        except Exception:
            pass
        ddc = _windows_ddc_brightness(None)
        if ddc is not None:
            return {"supported": True, "brightness": ddc, "method": "ddc"}
        return {"supported": False, "brightness": None, "method": "none"}

    if shutil.which("brightnessctl"):
        cur = subprocess.run(["brightnessctl", "g"], capture_output=True, text=True, timeout=2).stdout.strip()
        mx = subprocess.run(["brightnessctl", "m"], capture_output=True, text=True, timeout=2).stdout.strip()
        if cur.isdigit() and mx.isdigit() and int(mx) > 0:
            return {"supported": True, "brightness": round(int(cur) * 100 / int(mx)), "method": "brightnessctl"}
    for bl in Path("/sys/class/backlight").glob("*"):
        try:
            cur_v = int((bl / "brightness").read_text().strip())
            max_v = int((bl / "max_brightness").read_text().strip())
            if max_v > 0:
                return {"supported": True, "brightness": round(cur_v * 100 / max_v), "method": "sysfs"}
        except Exception:
            continue
    return {"supported": False, "brightness": None, "method": "none"}


def set_display_brightness(level: int) -> dict:
    """Set display brightness between 0 and 100."""
    lvl = max(0, min(100, int(level)))
    if os.name == "nt":
        wmi_ok = False
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", f"$m = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods -ErrorAction SilentlyContinue; if ($m) {{ $m | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=1; Brightness={lvl}}} | Out-Null; 'OK' }}"],
                capture_output=True, text=True, timeout=4, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            wmi_ok = "OK" in res.stdout
        except Exception:
            pass
        ddc_val = _windows_ddc_brightness(lvl)
        if wmi_ok or ddc_val is not None:
            return {"updated": True, "brightness": lvl}
        raise RuntimeError("Monitor does not support WMI or DDC/CI brightness control")

    if shutil.which("brightnessctl"):
        res = subprocess.run(["brightnessctl", "set", f"{lvl}%"], capture_output=True, timeout=3)
        if res.returncode == 0:
            return {"updated": True, "brightness": lvl}
    raise RuntimeError("Install brightnessctl for Linux brightness control")


def turn_display_off(run_desktop_fn=None) -> dict:
    """Turn off monitors without putting the PC to sleep."""
    if os.name == "nt":
        def _off() -> None:
            user32 = ctypes.windll.user32
            user32.SendNotifyMessageW.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
            user32.SendNotifyMessageW(0xFFFF, 0x0112, 0xF170, 2)
        if run_desktop_fn:
            run_desktop_fn(_off)
        else:
            _off()
        return {"sent": True, "display_off": True}

    for cmd in (["xset", "dpms", "force", "off"], ["wlopm", "--off", "*"]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, capture_output=True, check=False, timeout=3)
            return {"sent": True, "display_off": True}
    raise RuntimeError("Install xset or wlopm to turn off Linux display")


# ---------------------------------------------------------------------------
# 6. Safe Process Kill
# ---------------------------------------------------------------------------
def kill_process_safe(pid: int) -> dict:
    """Safely terminate a non-system process by PID."""
    if not psutil:
        raise RuntimeError("psutil is required to terminate processes")
    if type(pid) is not int or pid <= 4 or pid == os.getpid():
        raise ValueError("Cannot terminate protected or invalid PID")
    try:
        proc = psutil.Process(pid)
        pname = (proc.name() or "").strip()
    except psutil.NoSuchProcess:
        raise FileNotFoundError(f"Process {pid} no longer exists")
    except psutil.AccessDenied:
        raise PermissionError(f"Access denied for process {pid}")

    if pname.lower() in PROTECTED_PROCESS_NAMES:
        raise PermissionError(f"Refusing to terminate critical system process: {pname}")

    try:
        proc.terminate()
    except psutil.AccessDenied:
        raise PermissionError(f"Access denied terminating {pname} ({pid})")
    return {"killed": True, "pid": pid, "name": pname}


# ---------------------------------------------------------------------------
# 7. Custom Studio Pro Buttons
# ---------------------------------------------------------------------------
def sanitize_custom_buttons(raw: object) -> list[dict]:
    """Validate and normalize custom Studio Pro buttons saved via local /desktop."""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw[:24]:
        if not isinstance(item, dict):
            continue
        bid = re.sub(r"[^a-zA-Z0-9_-]", "", str(item.get("id") or ""))[:32] or f"btn_{len(out) + 1}"
        if bid in seen:
            bid = f"{bid}_{len(out) + 1}"
        label = str(item.get("label") or "").strip()[:36]
        icon = str(item.get("icon") or "⚡").strip()[:8] or "⚡"
        kind = str(item.get("kind") or "").strip().lower()
        target = str(item.get("target") or "").strip()[:300]
        if not label or not target or kind not in {"url", "app", "hotkey"}:
            continue
        if kind == "url" and not (target.startswith("http://") or target.startswith("https://")):
            continue
        if kind == "hotkey" and target not in HOTKEYS:
            continue
        seen.add(bid)
        out.append({"id": bid, "label": label, "icon": icon, "kind": kind, "target": target})
    return out


def run_custom_button(button: dict, run_desktop_fn=None) -> dict:
    """Execute one pre-configured custom Studio Pro button."""
    kind = button.get("kind")
    target = str(button.get("target") or "")
    if kind == "hotkey":
        return send_hotkey(target, run_desktop_fn=run_desktop_fn)
    if kind == "url":
        if not (target.startswith("http://") or target.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        if os.name == "nt":
            if run_desktop_fn:
                run_desktop_fn(lambda: os.startfile(target))
            else:
                os.startfile(target)
        else:
            subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"sent": True, "id": button.get("id"), "label": button.get("label")}
    if kind == "app":
        if os.name == "nt":
            def _launch() -> None:
                os.startfile(target)
            if run_desktop_fn:
                run_desktop_fn(_launch)
            else:
                _launch()
        else:
            exe = target.split()[0]
            if not shutil.which(exe) and not Path(target).exists():
                raise RuntimeError(f"Application not found: {target}")
            subprocess.Popen([target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return {"sent": True, "id": button.get("id"), "label": button.get("label")}
    raise ValueError("Unsupported custom button kind")


# ---------------------------------------------------------------------------
# 8. Wake-on-LAN Diagnostics & Auto-Fix
# ---------------------------------------------------------------------------
def diagnose_wol() -> dict:
    """Inspect OS network adapter WoL readiness and Fast Startup state."""
    checks: list[dict] = []
    if os.name == "nt":
        ps = r"""
$out = @()
$adapters = Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'Up' }
foreach ($a in $adapters) {
    $props = Get-NetAdapterAdvancedProperty -Name $a.Name -ErrorAction SilentlyContinue
    $wmp = $props | Where-Object { $_.DisplayName -match 'Magic Packet|Wake on Magic' } | Select-Object -First 1
    $eee = $props | Where-Object { $_.DisplayName -match 'Energy[- ]Efficient|Green Ethernet' } | Select-Object -First 1
    $pm = Get-NetAdapterPowerManagement -Name $a.Name -ErrorAction SilentlyContinue
    $out += [PSCustomObject]@{
        name = $a.Name
        desc = $a.InterfaceDescription
        mac = $a.MacAddress
        media = $a.MediaType
        magic_prop = if ($wmp) { "$($wmp.DisplayValue)" } else { "Unknown" }
        eee_prop = if ($eee) { "$($eee.DisplayValue)" } else { "Unknown" }
        pm_magic = if ($pm) { "$($pm.WakeOnMagicPacket)" } else { "Unknown" }
    }
}
$fast = (Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -Name HiberbootEnabled -ErrorAction SilentlyContinue).HiberbootEnabled
[PSCustomObject]@{ adapters = $out; fast_startup = $fast } | ConvertTo-Json -Depth 4
"""
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            data = json.loads(res.stdout or "{}")
            adapters = data.get("adapters") or []
            if isinstance(adapters, dict):
                adapters = [adapters]
            if not adapters:
                checks.append({
                    "id": "no_adapter",
                    "title": "Активный сетевой адаптер",
                    "ok": False,
                    "value": "Не найден",
                    "hint": "Подключите Ethernet или Wi-Fi адаптер.",
                })
            for a in adapters:
                name = str(a.get("name") or "Adapter")
                mp = str(a.get("magic_prop") or "Unknown")
                pm = str(a.get("pm_magic") or "Unknown")
                eee = str(a.get("eee_prop") or "Unknown")
                magic_ok = any(k in mp.lower() for k in ("enabled", "включ")) or any(k in pm.lower() for k in ("enabled", "true"))
                checks.append({
                    "id": f"wol_{name}",
                    "title": f"{name}: Wake on Magic Packet",
                    "ok": magic_ok,
                    "value": f"Драйвер: {mp} · Питание: {pm}",
                    "hint": "Включите Wake on Magic Packet в диспетчере устройств или нажмите Авто-исправление.",
                })
                if "enabled" in eee.lower() or "включ" in eee.lower():
                    checks.append({
                        "id": f"eee_{name}",
                        "title": f"{name}: Energy-Efficient Ethernet",
                        "ok": False,
                        "value": eee,
                        "hint": "Рекомендуется отключить EEE, если ПК не просыпается из выключенного состояния.",
                    })
            fast = data.get("fast_startup")
            checks.append({
                "id": "fast_startup",
                "title": "Windows Fast Startup (Быстрый запуск)",
                "ok": fast == 0,
                "value": "Выключен (оптимально для WoL)" if fast == 0 else "Включён (может блокировать WoL)",
                "hint": "Быстрый запуск Windows переводит ПК в гибридный сон S4, где многие сетевые карты отключают WoL.",
            })
        except Exception as exc:
            checks.append({"id": "err", "title": "Диагностика WoL", "ok": False, "value": str(exc), "hint": ""})
        return {"ok": True, "os": "windows", "checks": checks, "all_ok": bool(checks) and all(c["ok"] for c in checks)}

    if shutil.which("ethtool"):
        try:
            ifaces = [p.name for p in Path("/sys/class/net").iterdir() if p.name != "lo" and (p / "operstate").read_text().strip() == "up"]
            for iface in ifaces:
                out = subprocess.run(["ethtool", iface], capture_output=True, text=True, timeout=3).stdout
                m = re.search(r"Wake-on:\s*(\S+)", out)
                val = m.group(1) if m else "unknown"
                checks.append({
                    "id": f"wol_{iface}",
                    "title": f"{iface}: Wake-on-LAN",
                    "ok": "g" in val,
                    "value": f"Wake-on: {val}",
                    "hint": f"Выполните: sudo ethtool -s {iface} wol g",
                })
        except Exception as exc:
            checks.append({"id": "err", "title": "ethtool", "ok": False, "value": str(exc), "hint": ""})
    else:
        checks.append({"id": "ethtool", "title": "ethtool", "ok": False, "value": "Не установлен", "hint": "Установите ethtool для проверки WoL."})
    return {"ok": True, "os": "linux", "checks": checks, "all_ok": bool(checks) and all(c["ok"] for c in checks)}


def autofix_wol_windows() -> dict:
    """Request UAC elevation to enable Wake on Magic Packet and disable Fast Startup."""
    if os.name != "nt":
        return {"ok": False, "error": "Авто-исправление UAC доступно только в Windows."}
    ps = (
        "$adapters = Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' }; "
        "foreach ($a in $adapters) { "
        "  try { Set-NetAdapterPowerManagement -Name $a.Name -WakeOnMagicPacket Enabled -ErrorAction SilentlyContinue } catch {}; "
        "  try { Get-NetAdapterAdvancedProperty -Name $a.Name | Where-Object { $_.DisplayName -match 'Magic Packet|Wake on Magic' } | ForEach-Object { Set-NetAdapterAdvancedProperty -Name $a.Name -DisplayName $_.DisplayName -DisplayValue 'Enabled' -ErrorAction SilentlyContinue } } catch {}; "
        "}; "
        "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Power' -Name HiberbootEnabled -Value 0 -ErrorAction SilentlyContinue"
    )
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", f'-NoProfile -Command "{ps}"', None, 0)
    if rc <= 32:
        return {"ok": False, "error": "Запрос UAC отклонён пользователем."}
    return {"ok": True, "message": "✅ Запущено авто-исправление WoL и отключение Fast Startup (подтвердите UAC)"}


# ---------------------------------------------------------------------------
# 9. GitHub Releases Update Checker
# ---------------------------------------------------------------------------
def _parse_ver(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v or "")
    return tuple(int(x) for x in nums[:3]) if nums else (0, 0, 0)


def check_github_updates(repo: str = GITHUB_REPO, current_version: str = APP_VERSION) -> dict:
    """Query GitHub Releases API for the latest published version."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"PCPhoneRemote/{current_version}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        latest_tag = str(data.get("tag_name") or "").lstrip("vV")
        release_url = str(data.get("html_url") or f"https://github.com/{repo}/releases/latest")
        assets = data.get("assets") or []
        installer_url = ""
        for a in assets:
            name = str(a.get("name") or "")
            if (os.name == "nt" and name.endswith(".exe")) or (os.name != "nt" and name.endswith(".run")):
                installer_url = str(a.get("browser_download_url") or "")
                break
        update_avail = _parse_ver(latest_tag) > _parse_ver(current_version)
        return {
            "ok": True,
            "current_version": current_version,
            "latest_version": latest_tag or current_version,
            "update_available": update_avail,
            "release_url": release_url,
            "installer_url": installer_url or release_url,
            "notes": str(data.get("body") or "")[:600],
        }
    except Exception as exc:
        return {
            "ok": False,
            "current_version": current_version,
            "latest_version": current_version,
            "update_available": False,
            "error": str(exc),
        }
