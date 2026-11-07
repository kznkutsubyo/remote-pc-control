"""Update an existing local installation, preserving its launch arguments and PIN."""
import argparse
import ast
import datetime
import json
import os
from pathlib import Path
import py_compile
import shutil
import subprocess
import time
import urllib.request

import psutil

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--pid", type=int, required=True)
parser.add_argument("--target", type=Path, required=True)
args = parser.parse_args()
target = args.target.resolve(strict=True)
source = Path(__file__).resolve().parents[1] / "pc-phone-remote"
process = psutil.Process(args.pid)
if Path(process.cwd()).resolve() != target or process.name().lower() not in {"python.exe", "pythonw.exe"}:
    raise SystemExit("Process does not match the specified Python server installation")
command = process.cmdline()
if not any(Path(part).name == "app.py" for part in command):
    raise SystemExit("Selected process is not app.py")
if source.resolve() == target:
    raise SystemExit("This updater is for a separate installed copy")
for name in ("app.py", "companion.py", "relay_server.py", "relay_agent.py", "server_tray.py"):
    py_compile.compile(str(source / name), doraise=True)
backup = target / "backups" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
backup.mkdir(parents=True)
files = ("app.py", "companion.py", "share.html", "server_tray.py", "requirements.txt",
         "install-deps.bat", "install-command-tasks.ps1", "config.example.json", "README.md", "start-hidden.vbs")
for name in (*files, "config.json"):
    if (target / name).exists():
        shutil.copy2(target / name, backup / name)
config_path = target / "config.json"
config = json.loads(config_path.read_text("utf-8")) if config_path.exists() else {}
if "--pin" in command:
    pin_index = command.index("--pin")
    config["pin"] = command[pin_index + 1]
    del command[pin_index:pin_index + 2]
elif not config.get("pin"):
    # Read the old default without importing or running the old application.
    tree = ast.parse((target / "app.py").read_text("utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(name, ast.Name) and name.id == "DEFAULT_PIN" for name in node.targets):
            config["pin"] = ast.literal_eval(node.value)
config.setdefault("rdp", {"host": "", "port": 3389, "username": "", "gateway": ""})
process.terminate()
process.wait(timeout=8)
try:
    for name in files:
        shutil.copy2(source / name, target / name)
    config_path.write_text(json.dumps(config, indent=2), "utf-8")
    log = (target / "server.log").open("ab")
    subprocess.Popen(command, cwd=target, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    log.close()
    port = command[command.index("--port") + 1] if "--port" in command else "8765"
    for attempt in range(20):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                if response.headers.get("Server", "").startswith("PCPhoneRemote/2.0"):
                    print(f"Updated local server to v2. Backup: {backup}")
                    break
        except OSError:
            pass
        time.sleep(.25)
    else:
        raise RuntimeError("Server health check failed. Backup was retained; see server.log.")
except Exception:
    print(f"Update failed. Backup available at {backup}")
    raise
