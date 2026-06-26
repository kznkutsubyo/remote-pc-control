# PC Phone Remote

PC Phone Remote is a small remote-control system for your own Windows PC. It lets you use an Android phone as a clean control panel for common actions such as muting sound, locking the desktop, putting the PC to sleep, restarting, and shutting down.

The project includes a Windows-side Python server, a native Android app, and an optional relay mode for controlling the PC when the phone is not on the same network.

> Built for personal administration of your own devices. Do not use it on computers you do not own or do not have permission to control.

## Features

- Native Android app with a polished dark interface.
- Multiple device profiles in the Android app.
- Bottom-tab navigation for Remote, Devices, and Settings.
- Local Wi-Fi control over HTTP.
- Optional remote mode through a public relay server.
- PIN-protected command access.
- Windows autostart through Task Scheduler.
- Optional Task Scheduler command tasks for locked-screen power commands.
- Hidden background launch with `pythonw.exe`.
- Multilingual Android UI:
  - English
  - Russian
  - Ukrainian
  - Slovak
  - Czech
  - Japanese
  - German
  - Spanish
  - French
  - Polish
- Commands:
  - toggle mute
  - lock Windows
  - sleep
  - restart
  - shutdown

## Project Structure

```text
.
+-- pc-phone-remote/
|   +-- app.py                # Local Windows HTTP server
|   +-- relay_server.py       # Public relay server for remote access
|   +-- relay_agent.py        # PC-side relay polling agent
|   +-- run.bat               # Manual local server launcher
|   +-- start-hidden.vbs      # Hidden autostart launcher
|   +-- start-relay-agent.bat # Relay agent launcher
|   +-- README.md             # Local server notes
|   +-- README_REMOTE.md      # Relay mode notes
|
+-- pc-phone-remote-android/
    +-- app/
    |   +-- src/main/java/com/pcphoneremote/app/MainActivity.java
    +-- gradlew.bat
    +-- README.md
```

## How It Works

### Local Network Mode

Use this when the phone and PC are on the same Wi-Fi or LAN.

```text
Android phone -> Windows PC server -> Windows command
```

The Android app sends requests directly to the PC server, for example:

```text
http://192.168.1.25:8765
```

### Remote Relay Mode

Use this when the phone is outside the home network.

```text
Android phone -> public relay server -> PC relay agent -> Windows command
```

The PC opens an outgoing connection to the relay and polls for commands. This avoids router port forwarding and avoids exposing the local Windows server directly to the internet.

## Requirements

### Windows PC

- Windows 10 or Windows 11
- Python 3
- Network access between phone and PC for local mode

### Android App

- Android Studio or Gradle for building from source
- Android device or emulator

### Remote Relay Mode

- A public server, VPS, or hosting platform
- HTTPS strongly recommended
- A long random `RELAY_AGENT_TOKEN`

## Quick Start: Local Mode

Start the Windows server:

```powershell
cd "pc-phone-remote"
$env:REMOTE_PIN = "<your-pin>"
python app.py
```

The terminal prints one or more local URLs:

```text
http://192.168.1.25:8765
```

Open the Android app and enter:

```text
IP:   192.168.1.25
Port: 8765
PIN:  use the same PIN you set in REMOTE_PIN
```

Then tap **Test connection**.

## Windows Autostart

The server can be launched automatically after Windows logon using Task Scheduler.

This project includes:

```text
pc-phone-remote/start-hidden.vbs
```

It starts the server with `pythonw.exe`, so no console window stays open.

Example Task Scheduler action:

```text
Program:   wscript.exe
Argument:  "C:\path\to\pc-phone-remote\start-hidden.vbs"
Start in:  C:\path\to\pc-phone-remote
```

## Build the Android App

From PowerShell:

```powershell
cd "pc-phone-remote-android"
.\gradlew.bat assembleDebug
```

The debug APK will be created at:

```text
pc-phone-remote-android/app/build/outputs/apk/debug/app-debug.apk
```

Install it on your phone and configure the PC address, port, and PIN in the app.

## Remote Mode Setup

### 1. Run the Relay Server

On a public server:

```powershell
cd "pc-phone-remote"
$env:RELAY_PIN = "<your-pin>"
$env:RELAY_AGENT_TOKEN = "replace-with-a-long-random-secret"
python relay_server.py --host 0.0.0.0 --port 8080
```

Put HTTPS in front of the relay using your hosting provider, reverse proxy, or load balancer.

Example public relay URL:

```text
https://remote.example.com
```

### 2. Run the PC Relay Agent

On the Windows PC:

```powershell
cd "pc-phone-remote"
$env:RELAY_URL = "https://remote.example.com"
$env:RELAY_AGENT_TOKEN = "replace-with-the-same-long-random-secret"
python relay_agent.py
```

### 3. Configure the Android App

In the Android app, put the full relay URL into the IP field:

```text
https://remote.example.com
```

When the IP field starts with `http://` or `https://`, the app uses it as a full server URL and ignores the port field.

Keep the PIN set to your relay PIN.

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
| `RELAY_PIN` | PIN required by the phone app |
| `RELAY_AGENT_TOKEN` | Secret token used by the PC agent |
| `RELAY_HOST` | Relay bind address |
| `RELAY_PORT` | Relay server port |

### Relay Agent

| Variable | Description |
| --- | --- |
| `RELAY_URL` | Public relay URL |
| `RELAY_AGENT_TOKEN` | Same secret token used by the relay server |
| `RELAY_POLL_INTERVAL` | Delay after relay errors |

## Security Notes

- Change the default PIN before sharing or deploying.
- Do not expose `app.py` directly to the public internet.
- Use HTTPS for relay mode.
- Use a long random `RELAY_AGENT_TOKEN`.
- Keep the relay private to your own devices.
- The app is intended for explicit, authorized control of your own Windows PC.

## Limitations

- Turning on a fully powered-off PC is not handled by this app. That requires Wake-on-LAN support and separate network configuration.
- Local mode requires the phone and PC to be on the same network.
- Remote mode requires a public relay host.
- The Android APK produced by `assembleDebug` is a debug build, not a signed release build for app stores.

## Roadmap Ideas

- Release APK signing.
- Better relay deployment templates.
- Wake-on-LAN helper.
- Command history in the Android app.
- HTTPS setup guide with Caddy or Nginx.

## License

MIT. See [LICENSE](LICENSE).
