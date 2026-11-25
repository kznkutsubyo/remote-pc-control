# PC Phone Remote 2.4.0

- **Live Screen View & Coordinate Tap**: capture JPEG snapshots or stream MJPEG (`/api/screen.mjpg`) with multi-monitor selection and direct Left / Right / Double click on Android, iOS, and Web PWA (`/app`).
- **Live Unicode Keyboard & Hotkeys**: type directly into the active Windows or Linux window via `SendInput` (`KEYEVENTF_UNICODE`) / `wtype` / `xdotool`, plus quick hotkeys (`Alt+Tab`, `Win+D`, `Alt+F4`, `Ctrl+Shift+Esc`, `Ctrl+C/V`, language switch).
- **Real OS Clipboard Sync**: 1-tap Push/Pull directly with the real Windows (`CF_UNICODETEXT`) or Linux (`wl-clipboard`/`xclip`) clipboard.
- **Audio Output Switcher & App Volume Mixer**: switch default speakers/headset/HDMI output and adjust or mute per-application audio sessions (`CoreAudio` on Windows, `pactl` on Linux).
- **Display Brightness & Screen Off**: adjust monitor brightness (WMI + `dxva2` DDC/CI on Windows, `brightnessctl`/`sysfs` on Linux) and turn off displays without putting the PC to sleep.
- **Safe Process Termination**: terminate non-system processes with confirmation (`processes.kill`) directly from Android, iOS, or PWA.
- **Studio Pro Custom Button Builder**: create custom Website URL, PC App, or Hotkey buttons in the Desktop Control Center (`/desktop`) synced to all phone clients.
- **Wake-on-LAN Diagnostic Wizard & Local HTTPS**: inspect Windows adapter WoL / Fast Startup status (`wol_diagnose`) with 1-click UAC autofix, plus optional self-signed local TLS (`--https` + `/api/local/cert`) for full PWA Service Worker support.
- **Upgraded System Tray & GitHub Update Checker**: quick native Tkinter QR popup, 1-click Copy PIN, live client connection notifications, and automatic GitHub release checks.
- **Native Mobile Extras**: built-in `AVFoundation` QR scanner + **Siri Shortcuts (`AppIntents`)** on iOS (`PCPhoneRemote-v2.4.0.ipa`), plus **Android Quick Settings Tiles** (Lock, Play/Pause, Screen Off) and **Home Screen Widget**.

## Downloads

- `PCPhoneRemote-v2.4.0.apk`: Android release (with Quick Settings Tiles & Home Screen Widget).
- `PCPhoneRemote-v2.4.0.ipa`: Native iOS (`arm64`) unsigned IPA with QR scanner & Siri Shortcuts (sideload via Sideloadly / AltStore / TrollStore).
- `PCPhoneRemote-Setup.exe`: Windows installer & animated desktop control center launcher.
- `PCPhoneRemote-Linux-Installer.run`: per-user Linux installer.
- `PCPhoneRemote-Windows-v2.4.0.zip`: portable Windows package and native x64 sign-in binaries.
- `PCPhoneRemote-Relay-v2.4.0.zip`: self-hosted relay sources.
- `PCPhoneRemote-iOS-Source-v2.4.0.zip`: SwiftUI sources for local Xcode signing/building.
- `SHA256SUMS.txt`: download checksums.

Container: `ghcr.io/kznkutsubyo/remote-pc-control-relay:2.4.0`.
