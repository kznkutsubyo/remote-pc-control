# PC Phone Remote Android

Native Android remote for the local Windows server in `pc-phone-remote`.

## What it does

- Saves PC IP, port, and PIN.
- Supports multiple saved device profiles.
- Has first-run onboarding for adding the first PC.
- Imports PC setup codes from the Windows pairing page.
- Supports dark and light themes.
- Uses separate Remote, Devices, and Settings tabs.
- Sends `mute`, `lock`, `sleep`, `restart`, and `shutdown` commands.
- Uses plain local HTTP, so the Windows server must be running on the PC.

No real IP or PIN is bundled. Add your own PC in the **Devices** tab.

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

For a local release-style APK:

```powershell
.\gradlew.bat assembleRelease
```

Output:

```text
pc-phone-remote-android\app\build\outputs\apk\release\app-release.apk
```

The local release build uses the debug signing key for easy manual installation.

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

To import a PC profile faster, open this page on the PC after the server starts:

```text
http://127.0.0.1:8765/pair
```

Scan the QR code with the phone camera, copy the setup code, then paste it into:

```text
Devices -> Import setup
```
