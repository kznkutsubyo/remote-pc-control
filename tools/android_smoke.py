"""Exercise the native app against the harmless loopback UI fixture."""
import os
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts"
OUT.mkdir(exist_ok=True)
ADB = Path(os.environ["LOCALAPPDATA"]) / "Android/Sdk/platform-tools/adb.exe"


def adb(*args):
    result = subprocess.run([str(ADB), "-s", "emulator-5554", *args], capture_output=True, check=True)
    return result.stdout.decode("utf-8", errors="replace")


def tree():
    adb("shell", "uiautomator", "dump", "/sdcard/window.xml")
    return ET.fromstring(adb("shell", "cat", "/sdcard/window.xml"))


def tap(label):
    nodes = list(tree().iter("node"))
    for node in nodes:
        if label.casefold() in (node.get("text", "").casefold(), node.get("content-desc", "").casefold()):
            x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds")))
            adb("shell", "input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2))
            return
    raise AssertionError(f"UI element not found: {label}")


def screenshot(name):
    time.sleep(.5)
    adb("shell", "screencap", "-p", "/sdcard/remote.png")
    adb("pull", "/sdcard/remote.png", str(OUT / (name + ".png")))


if __name__ == "__main__":
    adb("reverse", "tcp:8877", "tcp:8877")
    tap("\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c")
    fields = [n for n in tree().iter("node") if n.get("class") == "android.widget.EditText"]
    assert len(fields) == 4
    for index, value in enumerate(("Studio%sPC", "127.0.0.1", "8877", "preview-only")):
        node = [n for n in tree().iter("node") if n.get("class") == "android.widget.EditText"][index]
        x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds")))
        adb("shell", "input", "tap", str((x1+x2)//2), str((y1+y2)//2))
        adb("shell", "input", "keyevent", "KEYCODE_MOVE_END")
        for _ in range(len(node.get("text", ""))):
            adb("shell", "input", "keyevent", "KEYCODE_DEL")
        adb("shell", "input", "text", value)
        adb("shell", "input", "keyevent", "KEYCODE_BACK")
    screenshot("device-editor")
    tap("\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u043e")
    screenshot("devices-dark")
    tap("Studio PC")
    tap("\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c")
    time.sleep(1)
    nodes = tree()
    assert any("%" in n.get("text", "") for n in nodes.iter("node")), ET.tostring(nodes).decode()
    screenshot("remote-dark")
    tap("\u0422\u0435\u043c\u0430")
    time.sleep(.4)
    screenshot("remote-light")
    tap("\u041e\u0431\u043c\u0435\u043d")
    tap("\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c")
    time.sleep(.5)
    assert any(n.get("text") == "Welcome.txt" for n in tree().iter("node"))
    screenshot("exchange-light")
    tap("\u0422\u0435\u043c\u0430")
    time.sleep(.4)
    screenshot("exchange-dark")
    tap("\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438")
    screenshot("settings-dark")
    print("PASS: profile creation, authenticated status, both themes, remote files, settings")
