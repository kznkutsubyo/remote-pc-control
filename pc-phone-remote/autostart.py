"""Manage Windows user autostart for PC Phone Remote."""
from __future__ import annotations

import os
import sys
import winreg
from pathlib import Path

ROOT = Path(__file__).resolve().parent
START_VBS = ROOT / "start-hidden.vbs"
REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_VAL_NAME = "PCPhoneRemote"


def startup_shortcut_path() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "PC Phone Remote.vbs"


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, REG_VAL_NAME)
            if val:
                return True
    except OSError:
        pass
    return startup_shortcut_path().exists()


def enable() -> None:
    target_cmd = f'wscript.exe "{START_VBS}"'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, REG_VAL_NAME, 0, winreg.REG_SZ, target_cmd)

    # Also place a small helper VBS directly in the user Startup folder for 100% redundancy
    sc = startup_shortcut_path()
    try:
        sc.parent.mkdir(parents=True, exist_ok=True)
        sc.write_text(f'CreateObject("WScript.Shell").Run "{target_cmd.replace(chr(34), chr(34) * 2)}", 0, False\n', encoding="utf-8")
    except OSError:
        pass

    # Also register Task Scheduler task with highest privileges at logon
    try:
        import subprocess
        subprocess.run(
            ["schtasks", "/create", "/tn", "PC Phone Remote Server", "/tr", target_cmd, "/sc", "onlogon", "/rl", "highest", "/f"],
            capture_output=True,
            check=False
        )
    except Exception:
        pass


def disable() -> None:
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
        import subprocess
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
        print(f"Command: wscript.exe \"{START_VBS}\"")
