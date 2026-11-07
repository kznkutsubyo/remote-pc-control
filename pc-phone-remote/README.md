# PC Phone Remote

Windows companion server for PC Phone Remote 2.0: power and media controls, PC status, shared files/text and RDP connection settings. Use the Android app or the local web remote.

## Start

Install QR, tray and system-status dependencies once:

```powershell
cd "pc-phone-remote"
.\install-deps.bat
```

Double-click `run.bat`, or run:

```powershell
cd "pc-phone-remote"
$env:REMOTE_PIN = "<your-pin>"
python app.py
```

The terminal prints local URLs like:

```text
http://<your-pc-ip>:8765
```

Open that URL on your phone and enter the PIN.

Without a PIN override, first launch generates a random PIN in `config.json`. The configuration is local and ignored by Git. An existing configuration with an empty PIN must be filled in before launch.

## Pair Phone

After starting the server, open this on the PC:

```text
http://127.0.0.1:8765/pair
```

The page shows a setup code and, when optional dependencies are installed, a QR code. It is accessible only from this PC using a loopback address.

On Android:

```text
Devices -> Import setup
```

Paste the setup code and the app will create a device profile automatically.

## Tray Launcher

Run the server from a small Windows tray icon:

```powershell
cd "pc-phone-remote"
pythonw .\server_tray.py
```

The tray menu opens the remote, pairing page, shared folder and `/share` desktop transfer page, and can restart/stop the server or quit.

## Shared Data

Put files in `shared/` beside `app.py`, or choose a folder with `share_dir` in `config.json`. The Android Transfer tab uploads and downloads individual files up to 8 MiB. Uploads do not overwrite existing files. The shared text board is `shared/shared-note.txt` (up to 64 KiB).

The authenticated desktop page at `http://127.0.0.1:8765/share` can also exchange files and text. Sign in, then reopen `/share`. No clipboard monitoring or automatic execution of received files is performed.

## Windows Sign-In & Phone Unlock (E2E Encrypted)

PC Phone Remote 2.2 supports **two ways** to sign in to Windows from your phone:

### 1. Native Console Unlock (`windows-unlock` + `configure.bat`)
Unlocks the physical Windows lock screen directly from the phone using an End-to-End encrypted challenge-response protocol (`ECDH P-256` + `HKDF-SHA256` + `AES-256-GCM` + `ECDSA P-256` + `AndroidKeyStore`):
1. Build the native service and Credential Provider v2 once:
   ```powershell
   powershell -ExecutionPolicy Bypass -File ..\windows-unlock\build.ps1 -RunTests
   ```
2. Open `configure.bat` on the PC (Tab **«Вход в Windows с телефона»**), enter your Windows password once for local verification (`LogonUserW`), and copy the one-time `pcphone://enroll?...` code.
3. In the Android app, tap **«Привязать вход с телефона»** and paste the code.
4. To unlock the physical Windows lock screen in a test VM or host, install the provider from an elevated PowerShell prompt (`..\windows-unlock\install-unlock.ps1`).

### 2. Remote Desktop (RDP) Handoff
Configure the `rdp` object in `config.json` (or via `configure.bat` Tab 2): `host`, `port`, `username`, and optionally an RD `gateway`. The phone can launch an installed RDP client (`rdp://...`) as a fallback.

## Studio Pro Features

- **Interactive Touchpad & Presentation Remote**: Multi-gesture cursor pad (`move`, `left/right/double click`, `scroll`) and presentation hotkeys (`F5`, `←`, `→`, `Space`, `Esc`).
- **One-Tap Scenes**: `movie`, `night`, `work`, `presentation`, `away`.
- **Stream Deck Grid**: 8 instant desktop macros (`desktop`, `task_manager`, `screenshot`, `explorer`, `browser`, `mute`, `play_pause`, `lock`).
- **Wake-on-LAN & Process Monitor**: Send UDP Magic Packets directly from the phone or via `wol.wake`, and view top Windows processes (`processes.list`).

## Power Timer

Android can schedule a Windows shutdown in 1-180 minutes or cancel the pending shutdown. Windows forcibly closes programs at expiry, so save work before scheduling. Media keys require an unlocked session; file exchange and power commands do not.

## Autostart

To start the server after Windows logon, configure Task Scheduler with this action. Existing installations may already have this task.

Task name:

```text
PC Phone Remote Server
```

The task runs hidden:

```text
pc-phone-remote\start-hidden.vbs
```

An existing installation may write logs to:

```text
pc-phone-remote\server.log
```

## Locked Screen Commands

Install command tasks once so power commands can be launched through Windows Task Scheduler while the session is locked:

```powershell
cd "pc-phone-remote"
powershell -ExecutionPolicy Bypass -File .\install-command-tasks.ps1
```

The local server will use these tasks for `lock`, `sleep`, `restart`, and `shutdown` when they are available.

## Settings

- `REMOTE_PIN`: access PIN. No public default is provided; set your own before real use.
- `REMOTE_PORT`: server port. Default is `8765`.
- `REMOTE_HOST`: bind address. Default is `0.0.0.0`.
- `config.json`: generated local PIN, optional `share_dir`, and RDP connection settings. Environment/CLI PIN values override this file.

Example:

```powershell
$env:REMOTE_PIN = "<your-pin>"
$env:REMOTE_PORT = "9000"
python app.py
```

## Notes

- Windows Firewall may ask for network access the first time. Allow access for private networks if you want to open the page from your phone.
- Direct mode requires a reachable PC address. For outside-network file/text exchange, update both the relay and agent to v2; see the repository README. Keep HTTPS in front of a public relay.
- Turning the PC on from a full shutdown is different: the app cannot run while the PC is off. For that you need Wake-on-LAN support in BIOS/UEFI, Windows network adapter settings, and a separate device or phone app to send the wake packet.
