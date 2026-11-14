"""Cross-distribution Linux backend for audio, media, power, touchpad, scenes, Stream Deck & logind unlock."""
from __future__ import annotations

import getpass
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


def is_linux() -> bool:
    """Return True when running on Linux (or POSIX)."""
    return sys.platform.startswith("linux") or os.name != "nt"


def _run_ok(cmd: list[str], timeout: float = 4.0) -> subprocess.CompletedProcess | None:
    """Execute `cmd` if the binary exists, returning CompletedProcess on exit code 0."""
    exe = cmd[0]
    if not shutil.which(exe):
        return None
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        if res.returncode == 0:
            return res
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def _run_first(candidates: list[list[str]], timeout: float = 4.0) -> subprocess.CompletedProcess | None:
    """Run the first candidate command whose executable is available and succeeds."""
    for cmd in candidates:
        res = _run_ok(cmd, timeout=timeout)
        if res is not None:
            return res
    return None


def _spawn_detached(candidates: list[list[str]]) -> bool:
    """Spawn the first available desktop application or command detached."""
    for cmd in candidates:
        if not shutil.which(cmd[0]):
            continue
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except OSError:
            continue
    return False


def linux_session_id() -> str | None:
    """Resolve the active systemd-logind session ID for the current user."""
    env_sid = os.environ.get("XDG_SESSION_ID", "").strip()
    if env_sid:
        return env_sid
    res = _run_ok(["loginctl", "list-sessions", "--no-legend"])
    if not res:
        return None
    user = getpass.getuser()
    first_sid = None
    for line in res.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        if first_sid is None:
            first_sid = parts[0]
        if len(parts) >= 3 and parts[2] == user:
            return parts[0]
    return first_sid


def linux_session_locked() -> bool:
    """Return True if the current Linux desktop session appears locked."""
    sid = linux_session_id()
    if sid:
        res = _run_ok(["loginctl", "show-session", sid, "-p", "LockedHint", "--value"])
        if res is not None:
            val = res.stdout.strip().lower()
            if val in {"yes", "true", "1"}:
                return True
            if val in {"no", "false", "0"}:
                return False

    gnome_res = _run_ok([
        "gdbus", "call", "--session",
        "--dest", "org.gnome.ScreenSaver",
        "--object-path", "/org/gnome/ScreenSaver",
        "--method", "org.gnome.ScreenSaver.GetActive",
    ])
    if gnome_res and "true" in gnome_res.stdout.lower():
        return True

    kde_res = _run_ok(["qdbus", "org.freedesktop.ScreenSaver", "/ScreenSaver", "GetActive"])
    if kde_res and "true" in kde_res.stdout.lower():
        return True

    return False


def linux_unlock_session() -> tuple[bool, str]:
    """Unlock the active Linux desktop session via logind / DBus screensaver."""
    sid = linux_session_id()
    unlocked = False
    if sid and _run_ok(["loginctl", "unlock-session", sid]) is not None:
        unlocked = True
    elif _run_ok(["loginctl", "unlock-sessions"]) is not None:
        unlocked = True

    # Wake DPMS display if running on X11 and clear GNOME screensaver lock
    _run_ok(["xset", "dpms", "force", "on"])
    _run_ok([
        "gdbus", "call", "--session",
        "--dest", "org.gnome.ScreenSaver",
        "--object-path", "/org/gnome/ScreenSaver",
        "--method", "org.gnome.ScreenSaver.SetActive", "false",
    ])
    if unlocked:
        return True, "Linux session unlocked via logind"
    return False, "Could not unlock Linux session (ensure loginctl / polkit permissions allow unlock-session)"


def linux_unlock_status() -> dict:
    """Return unlock readiness metadata for Linux sessions."""
    user = getpass.getuser()
    host = os.uname().nodename if hasattr(os, "uname") else "linux"
    return {
        "available": True,
        "enrolled": True,
        "provider_installed": True,
        "device_id": "linux-logind",
        "device_name": host,
        "user_sid": f"linux:{user}",
        "qualified_user": f"{user}@{host}",
        "vault_mode": "linux_logind",
        "pc_pub": "",
        "pc_pub_fp": "",
    }


def _read_linux_audio_state() -> dict:
    """Query current volume percentage and mute flag via wpctl/pactl/amixer."""
    wp = _run_ok(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
    if wp:
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)", wp.stdout)
        muted = "[MUTED]" in wp.stdout.upper()
        if m:
            return {"volume": round(float(m.group(1)) * 100), "muted": muted}

    pa = _run_ok(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
    pm = _run_ok(["pactl", "get-sink-mute", "@DEFAULT_SINK@"])
    if pa:
        m = re.search(r"(\d+)%", pa.stdout)
        muted = bool(pm and "yes" in pm.stdout.lower())
        if m:
            return {"volume": int(m.group(1)), "muted": muted}
    return {}


def linux_send_media(key: str) -> dict:
    """Send volume or MPRIS/X11 media key events on Linux."""
    if key == "mute":
        _run_first([
            ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"],
            ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
            ["amixer", "-D", "pulse", "sset", "Master", "toggle"],
            ["amixer", "sset", "Master", "toggle"],
            ["xdotool", "key", "XF86AudioMute"],
        ])
    elif key == "volume_up":
        _run_first([
            ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"],
            ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"],
        ])
        _run_first([
            ["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", "5%+"],
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+5%"],
            ["amixer", "-D", "pulse", "sset", "Master", "5%+"],
            ["amixer", "sset", "Master", "5%+"],
            ["xdotool", "key", "XF86AudioRaiseVolume"],
        ])
    elif key == "volume_down":
        _run_first([
            ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%-"],
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-5%"],
            ["amixer", "-D", "pulse", "sset", "Master", "5%-"],
            ["amixer", "sset", "Master", "5%-"],
            ["xdotool", "key", "XF86AudioLowerVolume"],
        ])
    elif key in {"play_pause", "next", "previous"}:
        pctl_verb = {"play_pause": "play-pause", "next": "next", "previous": "previous"}[key]
        xkey = {"play_pause": "XF86AudioPlay", "next": "XF86AudioNext", "previous": "XF86AudioPrev"}[key]
        mpris_method = {
            "play_pause": "PlayPause",
            "next": "Next",
            "previous": "Previous",
        }[key]
        _run_first([
            ["playerctl", pctl_verb],
            ["dbus-send", "--print-reply", "--dest=org.mpris.MediaPlayer2.spotify",
             "/org/mpris/MediaPlayer2", f"org.mpris.MediaPlayer2.Player.{mpris_method}"],
            ["xdotool", "key", xkey],
            ["ydotool", "key", xkey],
        ])
    else:
        raise ValueError(f"Unsupported Linux media key: {key}")

    result = {"sent": True}
    if key in {"mute", "volume_up", "volume_down"}:
        result.update(_read_linux_audio_state())
    return result


def linux_run_power_command(command: str) -> None:
    """Execute power or session commands (mute, lock, sleep, restart, shutdown) on Linux."""
    if command == "mute":
        linux_send_media("mute")
        return
    if command == "lock":
        sid = linux_session_id()
        candidates = []
        if sid:
            candidates.append(["loginctl", "lock-session", sid])
        candidates.extend([
            ["loginctl", "lock-session"],
            ["xdg-screensaver", "lock"],
            ["dm-tool", "lock"],
            ["dbus-send", "--type=method_call", "--dest=org.gnome.ScreenSaver",
             "/org/gnome/ScreenSaver", "org.gnome.ScreenSaver.Lock"],
            ["qdbus", "org.freedesktop.ScreenSaver", "/ScreenSaver", "Lock"],
        ])
        if _run_first(candidates) is None:
            raise RuntimeError("No Linux screen lock utility (loginctl/xdg-screensaver) available")
        return
    if command == "sleep":
        if _run_first([["systemctl", "suspend"], ["loginctl", "suspend"]]) is None:
            raise RuntimeError("Failed to suspend Linux host (systemctl suspend)")
        return
    if command == "restart":
        if _run_first([["systemctl", "reboot"], ["loginctl", "reboot"], ["sudo", "-n", "reboot"]]) is None:
            raise RuntimeError("Failed to reboot Linux host (systemctl reboot)")
        return
    if command == "shutdown":
        if _run_first([["systemctl", "poweroff"], ["loginctl", "poweroff"], ["sudo", "-n", "poweroff"], ["shutdown", "-h", "now"]]) is None:
            raise RuntimeError("Failed to power off Linux host (systemctl poweroff)")
        return
    raise ValueError(f"Unknown command: {command}")


def linux_schedule_shutdown(minutes: int | None) -> dict:
    """Schedule or cancel a timed Linux shutdown using `shutdown` or `systemd-run --user`."""
    if minutes is None:
        _run_ok(["shutdown", "-c"])
        _run_ok(["systemctl", "--user", "stop", "pc-phone-remote-poweroff.timer"])
        return {"scheduled": False, "minutes": None}

    res = _run_first([
        ["shutdown", "-h", f"+{minutes}"],
        ["systemd-run", "--user", "--unit=pc-phone-remote-poweroff", f"--on-active={minutes * 60}s", "systemctl", "poweroff"],
    ])
    if res is None:
        raise RuntimeError("Linux rejected the shutdown timer (shutdown/systemd-run unavailable or lacks permissions)")
    return {"scheduled": True, "minutes": minutes}


def linux_open_folder(folder: Path) -> dict:
    """Open the shared folder in the user's Linux desktop file manager."""
    target = str(folder)
    opened = _spawn_detached([["xdg-open", target], ["gio", "open", target]])
    return {"opened": opened, "path": target}


def linux_handle_touchpad(payload: dict) -> dict:
    """Handle mouse move, click, scroll, and presentation/navigation keys on Linux (X11/Wayland)."""
    kind = payload.get("type") or payload.get("mode") or payload.get("op")
    has_xdotool = shutil.which("xdotool") is not None
    has_ydotool = shutil.which("ydotool") is not None
    has_wtype = shutil.which("wtype") is not None

    if kind == "move":
        dx = max(-400, min(400, int(payload.get("dx", 0))))
        dy = max(-400, min(400, int(payload.get("dy", 0))))
        if has_xdotool:
            _run_ok(["xdotool", "mousemove_relative", "--", str(dx), str(dy)])
        elif has_ydotool:
            _run_ok(["ydotool", "mousemove", "--", str(dx), str(dy)])
        else:
            try:
                import pyautogui
                pyautogui.moveRel(dx, dy, _pause=False)
            except Exception as exc:
                raise RuntimeError("Install xdotool or ydotool for Linux touchpad support") from exc
        return {"sent": True}

    if kind == "click":
        btn = payload.get("button", "left")
        if has_xdotool:
            if btn == "right":
                _run_ok(["xdotool", "click", "3"])
            elif btn == "double":
                _run_ok(["xdotool", "click", "--repeat", "2", "1"])
            else:
                _run_ok(["xdotool", "click", "1"])
        elif has_ydotool:
            if btn == "right":
                _run_ok(["ydotool", "click", "0xC1"])
            elif btn == "double":
                _run_ok(["ydotool", "click", "0xC0"])
                _run_ok(["ydotool", "click", "0xC0"])
            else:
                _run_ok(["ydotool", "click", "0xC0"])
        else:
            try:
                import pyautogui
                if btn == "right":
                    pyautogui.rightClick(_pause=False)
                elif btn == "double":
                    pyautogui.doubleClick(_pause=False)
                else:
                    pyautogui.click(_pause=False)
            except Exception as exc:
                raise RuntimeError("Install xdotool or ydotool for Linux mouse clicks") from exc
        return {"sent": True}

    if kind == "scroll":
        raw_delta = payload.get("delta")
        dy = int(raw_delta) if raw_delta is not None else int(payload.get("dy", 0)) * 120
        steps = max(1, min(10, abs(dy) // 60 or 2))
        if has_xdotool:
            btn = "4" if dy > 0 else "5"
            _run_ok(["xdotool", "click", "--repeat", str(steps), btn])
        elif has_ydotool:
            amt = steps if dy > 0 else -steps
            _run_ok(["ydotool", "mousemove", "-w", "--", "0", str(amt)])
        else:
            try:
                import pyautogui
                pyautogui.scroll(dy, _pause=False)
            except Exception as exc:
                raise RuntimeError("Install xdotool or ydotool for Linux scroll support") from exc
        return {"sent": True}

    if kind == "key":
        key_map = {
            "space": ("space", "space"),
            "enter": ("Return", "Return"),
            "backspace": ("BackSpace", "BackSpace"),
            "escape": ("Escape", "Escape"),
            "esc": ("Escape", "Escape"),
            "left": ("Left", "Left"),
            "up": ("Up", "Up"),
            "right": ("Right", "Right"),
            "down": ("Down", "Down"),
            "page_up": ("Prior", "Prior"),
            "page_down": ("Next", "Next"),
            "f5": ("F5", "F5"),
        }
        key = payload.get("key")
        if key not in key_map:
            raise ValueError(f"Unsupported key: {key}")
        x_sym, w_sym = key_map[key]
        if has_xdotool:
            _run_ok(["xdotool", "key", x_sym])
        elif has_wtype:
            _run_ok(["wtype", "-k", w_sym])
        else:
            try:
                import pyautogui
                pyautogui.press(key.replace("page_", "pg").replace("escape", "esc"), _pause=False)
            except Exception as exc:
                raise RuntimeError("Install xdotool or wtype for Linux keyboard input") from exc
        return {"sent": True}

    raise ValueError("Unsupported touchpad event")


def linux_run_scene(scene: str, command_runner=None) -> dict:
    """Execute one-tap desktop scenes on Linux."""
    if scene == "away":
        if command_runner:
            command_runner("lock")
        else:
            linux_run_power_command("lock")
    elif scene == "movie":
        for _ in range(3):
            linux_send_media("volume_down")
        linux_send_media("play_pause")
    elif scene == "night":
        linux_send_media("mute")
        linux_schedule_shutdown(60)
    elif scene == "work":
        linux_schedule_shutdown(None)
    elif scene == "presentation":
        linux_handle_touchpad({"mode": "key", "key": "f5"})
    else:
        raise ValueError(f"Unknown scene: {scene}")
    return {"sent": True, "scene": scene}


def linux_run_deck_macro(macro: str, share_dir: Path, downloads_dir: Path | None = None, command_runner=None) -> dict:
    """Execute Stream Deck macros on Linux."""
    if macro == "lock":
        if command_runner:
            command_runner("lock")
        else:
            linux_run_power_command("lock")
        return {"sent": True, "macro": macro}
    if macro == "mute":
        linux_send_media("mute")
        return {"sent": True, "macro": macro}
    if macro == "play_pause":
        linux_send_media("play_pause")
        return {"sent": True, "macro": macro}
    if macro == "desktop":
        if _run_first([["wmctrl", "-k", "on"], ["xdotool", "key", "super+d"], ["xdotool", "key", "ctrl+alt+d"]]) is None:
            raise RuntimeError("Install wmctrl or xdotool for Show Desktop on Linux")
        return {"sent": True, "macro": macro}
    if macro in {"task_manager", "taskmgr"}:
        launched = _spawn_detached([
            ["gnome-system-monitor"],
            ["plasma-systemmonitor"],
            ["ksysguard"],
            ["xfce4-taskmanager"],
            ["mate-system-monitor"],
            ["lxtask"],
            ["x-terminal-emulator", "-e", "htop"],
        ])
        return {"sent": launched, "macro": macro}
    if macro == "explorer":
        _spawn_detached([["xdg-open", str(Path.home())], ["gio", "open", str(Path.home())]])
        return {"sent": True, "macro": macro}
    if macro == "browser":
        _spawn_detached([["xdg-open", "https://www.google.com"]])
        return {"sent": True, "macro": macro}
    if macro == "screenshot":
        fname = f"Screenshot_PC_{int(time.time())}.png"
        out_path = share_dir / fname
        captured = _run_first([
            ["gnome-screenshot", "-f", str(out_path)],
            ["spectacle", "-b", "-n", "-o", str(out_path)],
            ["grim", str(out_path)],
            ["scrot", str(out_path)],
            ["import", "-window", "root", str(out_path)],
        ]) is not None
        if not captured:
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab()
                img.save(out_path, "PNG")
                captured = True
            except Exception:
                pass
        if captured and out_path.exists() and downloads_dir is not None:
            try:
                shutil.copy2(out_path, downloads_dir / fname)
            except OSError:
                pass
        return {"sent": True, "macro": macro, "file": fname if captured else ""}

    raise ValueError(f"Unknown Stream Deck macro: {macro}")
