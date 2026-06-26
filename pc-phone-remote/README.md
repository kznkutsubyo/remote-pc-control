# PC Phone Remote

Small local web remote for a Windows PC. Open it from your phone on the same Wi-Fi and use buttons for mute, lock, sleep, restart, and shutdown.

## Start

Double-click `run.bat`, or run:

```powershell
cd "pc-phone-remote"
$env:REMOTE_PIN = "<your-pin>"
python app.py
```

The terminal prints local URLs like:

```text
http://192.168.1.25:8765
```

Open that URL on your phone and enter the PIN.

## Autostart

This PC is set up to start the server after Windows logon using Task Scheduler.

Task name:

```text
PC Phone Remote Server
```

The task runs hidden:

```text
pc-phone-remote\start-hidden.vbs
```

Logs are written to:

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

Example:

```powershell
$env:REMOTE_PIN = "7391"
$env:REMOTE_PORT = "9000"
python app.py
```

## Notes

- Windows Firewall may ask for network access the first time. Allow access for private networks if you want to open the page from your phone.
- The PC and phone must be on the same network.
- Turning the PC on from a full shutdown is different: the app cannot run while the PC is off. For that you need Wake-on-LAN support in BIOS/UEFI, Windows network adapter settings, and a separate device or phone app to send the wake packet.
