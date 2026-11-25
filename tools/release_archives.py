"""Create explicit, secret-free release archives from build outputs and sources."""
import argparse
from pathlib import Path
import zipfile

from build_installers import ROOT, DIST_DIR, collect_pc_files, collect_unlock_files


def archive(name, files):
    with zipfile.ZipFile(DIST_DIR / name, "w", zipfile.ZIP_DEFLATED) as output:
        for source, target in files:
            output.write(source, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="2.3.1")
    args = parser.parse_args()
    if not __import__('re').fullmatch(r"\d+\.\d+\.\d+", args.version):
        parser.error("Version must be major.minor.patch")
    DIST_DIR.mkdir(exist_ok=True)
    common = [(ROOT / name, name) for name in ("LICENSE", "README.md", "RELEASE_NOTES.md")]
    native = collect_unlock_files()
    for required in ("PhoneUnlockProvider.dll", "PhoneUnlockService.exe", "PhoneUnlockSelfTest.exe"):
        if not any(source.name == required for source, _ in native):
            raise RuntimeError(f"Missing native build output: {required}")
    archive(f"PCPhoneRemote-Windows-v{args.version}.zip", collect_pc_files() + native + common + [(ROOT / "Install-PCPhoneRemote.bat", "Install-PCPhoneRemote.bat")])
    relay = ("app.py", "companion.py", "relay_server.py", "relay_agent.py", "unlock_ipc.py", "linux_support.py", "desktop_ui.py", "ios_pwa.py", "requirements.txt", "README_REMOTE.md")
    archive(f"PCPhoneRemote-Relay-v{args.version}.zip", [(ROOT / "pc-phone-remote" / name, name) for name in relay] + common)
    ios = ROOT / "pc-phone-remote-ios"
    files = [(path, str(path.relative_to(ROOT))) for path in ios.rglob("*") if path.is_file() and path.suffix in {".swift", ".json", ".plist", ".yml", ".md", ".png"} and not any(part in {"build", "DerivedData"} or part.endswith(".xcodeproj") for part in path.parts)]
    archive(f"PCPhoneRemote-iOS-Source-v{args.version}.zip", files + common)


if __name__ == "__main__":
    main()
