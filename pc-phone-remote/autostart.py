"""Manage Windows & Linux user autostart for PC Phone Remote."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

if os.name == "nt":
    import winreg
else:
    winreg = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parent
START_VBS = ROOT / "start-hidden.vbs"
APP_PY = ROOT / "app.py"
REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_VAL_NAME = "PCPhoneRemote"


def startup_shortcut_path() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "PC Phone Remote.vbs"


def linux_autostart_desktop_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "autostart" / "pc-phone-remote.desktop"


def linux_systemd_service_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "systemd" / "user" / "pc-phone-remote.service"


def is_enabled() -> bool:
    if os.name != "nt":
        if linux_autostart_desktop_path().exists():
            return True
        if linux_systemd_service_path().exists():
            return True
        return False

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, REG_VAL_NAME)
            if val:
                return True
    except OSError:
        pass
    return startup_shortcut_path().exists()


def enable() -> None:
    if os.name != "nt":
        python_exe = sys.executable or "python3"
        icon_path = ROOT / "assets" / "app_icon_512.png"
        desktop_file = linux_autostart_desktop_path()
        desktop_file.parent.mkdir(parents=True, exist_ok=True)
        desktop_file.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Version=1.0\n"
            "Name=PC Phone Remote\n"
            "Comment=Control PC from your phone over LAN\n"
            f'Exec="{python_exe}" "{APP_PY}"\n'
            f"Path={ROOT}\n"
            f"Icon={icon_path}\n"
            "Terminal=false\n"
            "X-GNOME-Autostart-enabled=true\n",
            encoding="utf-8",
        )
        svc_file = linux_systemd_service_path()
        try:
            svc_file.parent.mkdir(parents=True, exist_ok=True)
            svc_file.write_text(
                "[Unit]\n"
                "Description=PC Phone Remote Server\n"
                "After=network-online.target graphical-session.target\n\n"
                "[Service]\n"
                f'ExecStart="{python_exe}" "{APP_PY}"\n'
                f"WorkingDirectory={ROOT}\n"
                "Restart=on-failure\n"
                "RestartSec=5\n\n"
                "[Install]\n"
                "WantedBy=default.target\n",
                encoding="utf-8",
            )
            subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, check=False)
            subprocess.run(["systemctl", "--user", "enable", "--now", "pc-phone-remote.service"], capture_output=True, check=False)
        except Exception:
            pass
        return

    launcher_exe = ROOT / "PCPhoneRemote.exe"
    target_cmd = f'"{launcher_exe}" --server' if launcher_exe.exists() else f'wscript.exe "{START_VBS}"'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, REG_VAL_NAME, 0, winreg.REG_SZ, target_cmd)

    sc = startup_shortcut_path()
    try:
        sc.parent.mkdir(parents=True, exist_ok=True)
        sc.write_text(
            f'CreateObject("WScript.Shell").Run "{target_cmd.replace(chr(34), chr(34) * 2)}", 0, False\n',
            encoding="utf-8",
        )
    except OSError:
        pass

    try:
        subprocess.run(
            ["schtasks", "/create", "/tn", "PC Phone Remote Server", "/tr", target_cmd, "/sc", "onlogon", "/rl", "highest", "/f"],
            capture_output=True,
            check=False,
        )
    except Exception:
        pass


def disable() -> None:
    if os.name != "nt":
        for path in (linux_autostart_desktop_path(), linux_systemd_service_path()):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass
        try:
            subprocess.run(["systemctl", "--user", "disable", "--now", "pc-phone-remote.service"], capture_output=True, check=False)
        except Exception:
            pass
        return

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, REG_VAL_NAME)
    except OSError:
        pass

    sc = startup_shortcut_path()
    try:
        if sc.exists():
            sc.unlink()
    except OSError:
        pass

    try:
        subprocess.run(["schtasks", "/delete", "/tn", "PC Phone Remote Server", "/f"], capture_output=True, check=False)
    except Exception:
        pass


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    arg = (sys.argv[1:2] or ["--enable"])[0].lower()
    if arg in ("--disable", "-d"):
        disable()
        print("PC Phone Remote autostart disabled.")
    elif arg in ("--status", "-s"):
        status = "ENABLED" if is_enabled() else "DISABLED"
        print(f"PC Phone Remote autostart: {status}")
    else:
        enable()
        print("PC Phone Remote autostart successfully ENABLED!")
        if os.name == "nt":
            print(f'Command: wscript.exe "{START_VBS}"')
        else:
            print(f"Autostart file: {linux_autostart_desktop_path()}")
