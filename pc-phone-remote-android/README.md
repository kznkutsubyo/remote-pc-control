# PC Phone Remote Android

Native Android remote for the local Windows server in `pc-phone-remote`.

## What it does

- Saves PC IP, port, and PIN.
- Sends `mute`, `lock`, `sleep`, `restart`, and `shutdown` commands.
- Uses plain local HTTP, so the Windows server must be running on the PC.

Default settings:

- IP example: `192.168.1.25`
- Port: `8765`
- PIN: not bundled; set your own on the PC/server and enter the same value in the app

## Build APK

From PowerShell:

```powershell
cd "pc-phone-remote-android"
.\gradlew.bat assembleDebug
```

The APK will be here:

```text
pc-phone-remote-android\app\build\outputs\apk\debug\app-debug.apk
```

You can also build it from Android Studio:

1. Install Android Studio.
2. Open this folder:

```text
pc-phone-remote-android
```

3. Wait for Gradle sync.
4. Choose `Build > Build Bundle(s) / APK(s) > Build APK(s)`.
5. Install the generated APK on the phone.

## PC side

Start the Windows server first:

```powershell
cd "pc-phone-remote"
$env:REMOTE_PIN = "<your-pin>"
python app.py
```

The phone and PC must be on the same Wi-Fi/network.
