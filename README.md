# PC Phone Remote

Turn your Android phone into a clean remote control for your own Windows PC.

PC Phone Remote is a small Windows + Android project for quick computer actions from a phone: mute sound, lock the desktop, put the PC to sleep, restart, or shut it down. It supports local Wi-Fi control, multiple saved device profiles, a polished native Android interface, and an optional relay mode for access outside the home network.

> This project is intended only for personal administration of devices you own or have permission to control.

## Highlights

- Native Android app, not just a web page.
- Elegant dark UI with a light theme toggle.
- Animated theme switcher.
- Bottom navigation with Remote, Devices, and Settings tabs.
- Multiple device profiles saved on the phone.
- First-run onboarding for adding the first PC.
- Pairing page with setup code and optional QR code.
- Vector icon buttons for PC commands.
- Multilingual interface:
  English, Russian, Ukrainian, Slovak, Czech, Japanese, German, Spanish, French, and Polish.
- PIN-protected command access.
- Windows autostart through Task Scheduler.
- Hidden server launch with `pythonw.exe`.
- Optional Windows tray launcher.
- Optional Task Scheduler command tasks for locked-session power actions.
- Optional relay mode for remote access outside the local network.

## Commands

The Android app can send these commands to the Windows server:

| Command | Description |
| --- | --- |
| Mute | Toggle system mute |
| Lock | Lock the Windows session |
| Sleep | Put the PC to sleep |
| Restart | Restart Windows |
| Shutdown | Shut down Windows |

## Screens And Flow

The Android app is split into three main tabs:

| Tab | Purpose |
| --- | --- |
| Remote | Send commands to the selected computer |
| Devices | Add, edit, select, test, or delete PC profiles |
| Settings | Change language and switch between dark/light themes |

Each device profile stores:

- device name
- PC IP address or full relay URL
- port
- app PIN

No real IP address or PIN is bundled in the project. Configure your own values after installation.

## Project Structure

```text
.
|-- pc-phone-remote/
|   |-- app.py                     # Local Windows HTTP server
|   |-- relay_server.py            # Optional public relay server
|   |-- relay_agent.py             # PC-side relay polling agent
|   |-- server_tray.py             # Optional tray launcher
|   |-- requirements.txt           # Optional QR/tray dependencies
|   |-- install-deps.bat           # Dependency installer
|   |-- install-command-tasks.ps1   # Optional locked-session command tasks
|   |-- run.bat                    # Manual local server launcher
|   |-- start-hidden.vbs           # Hidden autostart launcher
|   |-- start-relay-agent.bat      # Relay agent launcher
|   |-- README.md                  # Windows server notes
|   `-- README_REMOTE.md           # Relay mode notes
|
`-- pc-phone-remote-android/
    |-- app/
    |   `-- src/main/java/com/pcphoneremote/app/MainActivity.java
    |-- gradlew.bat
    `-- README.md
```

## Requirements

### Windows PC

- Windows 10 or Windows 11
- Python 3
- Network access between phone and PC for local mode

### Android

- Android phone or emulator
- Android Studio or Gradle if building from source

### Optional Remote Relay

- Public server, VPS, or hosting platform
- HTTPS strongly recommended
- Long random relay agent token

## Quick Start: Local Wi-Fi Mode

Use this mode when the phone and PC are on the same Wi-Fi or LAN.

### 1. Start The Windows Server

```powershell
cd "pc-phone-remote"
.\install-deps.bat
$env:REMOTE_PIN = "<your-pin>"
python app.py
```

The server prints local addresses such as:

```text
http://<your-pc-ip>:8765
```

### 2. Add The PC In The Android App

Open this page on the PC:

```text
http://127.0.0.1:8765/pair
```

Scan the QR code with the phone camera, copy the setup code, then open the Android app:

```text
Devices -> Import setup
```

You can also create a profile manually:

```text
Name:  Home PC
IP:    <your-pc-ip>
Port:  8765
PIN:   the same PIN from REMOTE_PIN
```

Tap **Save device**, then **Test connection**.

### 3. Use The Remote

Go to the **Remote** tab and send commands to the selected device.

## Build The Android App

From PowerShell:

```powershell
cd "pc-phone-remote-android"
.\gradlew.bat assembleDebug
```

The debug APK will be created here:

```text
pc-phone-remote-android/app/build/outputs/apk/debug/app-debug.apk
```

For a locally installable release-style APK:

```powershell
.\gradlew.bat assembleRelease
```

Output:

```text
pc-phone-remote-android/app/build/outputs/apk/release/app-release.apk
```

This local release uses the debug signing key for convenience. Use a real private signing key before publishing anywhere.

## Windows Autostart

The server can start automatically after Windows logon using Task Scheduler.

This project includes:

```text
pc-phone-remote/start-hidden.vbs
```

It launches the server with `pythonw.exe`, so a console window does not stay open.

Example Task Scheduler action:

```text
Program:   wscript.exe
Argument:  "C:\path\to\pc-phone-remote\start-hidden.vbs"
Start in:  C:\path\to\pc-phone-remote
```

## Windows Tray Launcher

Install optional dependencies:

```powershell
cd "pc-phone-remote"
.\install-deps.bat
```

Then run:

```powershell
pythonw .\server_tray.py
```

The tray menu can open the remote page, open the pairing page, restart the server, stop the server, or quit the tray app.

## Locked-Session Power Commands

Some commands can be routed through Windows Task Scheduler so they still work while the Windows session is locked.

Install the optional tasks once:

```powershell
cd "pc-phone-remote"
powershell -ExecutionPolicy Bypass -File .\install-command-tasks.ps1
```

The local server will try to use those tasks for:

- lock
- sleep
- restart
- shutdown

Unlocking Windows or storing/auto-entering a Windows account PIN is intentionally not part of this project.

## Remote Access Outside The Local Network

Local mode works only when the phone can reach the PC directly. For outside-network access, the project includes an optional relay mode:

```text
Android phone -> public relay server -> PC relay agent -> Windows command
```

This avoids exposing the local Windows server directly to the public internet.

### 1. Start The Relay Server

On a public server:

```powershell
cd "pc-phone-remote"
$env:RELAY_PIN = "<your-pin>"
$env:RELAY_AGENT_TOKEN = "<long-random-secret>"
python relay_server.py --host 0.0.0.0 --port 8080
```

Put HTTPS in front of the relay using your hosting provider, reverse proxy, or load balancer.

Example relay URL:

```text
https://remote.example.com
```

### 2. Start The PC Relay Agent

On the Windows PC:

```powershell
cd "pc-phone-remote"
$env:RELAY_URL = "https://remote.example.com"
$env:RELAY_AGENT_TOKEN = "<same-long-random-secret>"
python relay_agent.py
```

### 3. Add A Relay Device In Android

In the **Devices** tab, put the full relay URL into the IP/URL field:

```text
https://remote.example.com
```

When the address starts with `http://` or `https://`, the app treats it as a full server URL and ignores the port field.

## Configuration

### Local Server

| Variable | Default | Description |
| --- | --- | --- |
| `REMOTE_PIN` | empty | PIN required by the app |
| `REMOTE_HOST` | `0.0.0.0` | Bind address |
| `REMOTE_PORT` | `8765` | Local server port |

### Relay Server

| Variable | Description |
| --- | --- |
| `RELAY_PIN` | PIN required by the Android app |
| `RELAY_AGENT_TOKEN` | Secret token used by the PC relay agent |
| `RELAY_HOST` | Relay bind address |
| `RELAY_PORT` | Relay server port |

### Relay Agent

| Variable | Description |
| --- | --- |
| `RELAY_URL` | Public relay URL |
| `RELAY_AGENT_TOKEN` | Same secret token used by the relay server |
| `RELAY_POLL_INTERVAL` | Delay after relay errors |

## Security Notes

- Use a unique PIN.
- Do not expose `app.py` directly to the public internet.
- Use relay mode with HTTPS for remote access.
- Use a long random `RELAY_AGENT_TOKEN`.
- Keep relay credentials private.
- Allow Windows Firewall access only for networks you trust.
- Use this only for your own devices or systems you are allowed to control.

## Limitations

- Turning on a fully powered-off PC is not handled by this app. That requires Wake-on-LAN support and separate network setup.
- Local Wi-Fi mode requires the phone and PC to be on the same reachable network.
- Remote access requires a public relay host or equivalent deployment.
- The APK from `assembleDebug` is a debug build, not a Play Store release build.
- Windows lock-screen unlock automation is intentionally not included.

## Roadmap Ideas

- Signed release APK.
- Wake-on-LAN helper.
- Command history.
- More relay deployment examples.
- HTTPS setup guide with Caddy or Nginx.
- Desktop tray icon for the Windows server.

## License

MIT. See [LICENSE](LICENSE).
