# PC Phone Remote Android

Native Android remote for the v2 Windows server in `pc-phone-remote`, with an optional HTTPS relay.

## What it does

- Saves PC IP, port, and PIN.
- Supports multiple saved device profiles.
- Has first-run onboarding for adding the first PC.
- Imports PC setup codes from the Windows pairing page.
- Supports dark and light themes.
- Uses separate Remote, Transfer, Devices, and Settings tabs.
- Animated tab indicator, theme slider/crossfade and button feedback, with reduced-motion support.
- Uploads/downloads files up to 8 MiB through the Android system file picker.
- Exchanges text and keeps separate local drafts for each PC.
- Shows CPU, memory, uptime and lock state on refresh.
- Adds media keys, a shutdown timer and per-device activity history.
- Opens an installed RDP client for Windows sign-in using connection settings from the PC.
- Sends `mute`, `lock`, `sleep`, `restart`, and `shutdown` commands.
- Supports local HTTP and HTTPS relay URLs. The v2 server/agent must remain running.

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

For direct mode, the phone must be able to reach the PC. For remote mode, update both the relay server and agent to v2. RDP sign-in uses a separate RDP connection or RD Gateway, not the application's HTTP relay.

To import a PC profile faster, open this page on the PC after the server starts:

```text
http://127.0.0.1:8765/pair
```

Scan the QR code with the phone camera, copy the setup code, then paste it into:

```text
Devices -> Import setup
```

Select a saved device to open the remote. Its refresh icon verifies the PIN and loads a status snapshot. Use Transfer for the PC's `shared/` folder and shared note. Windows passwords are entered in the RDP client, never in this app.

Russian and English include all new explanatory text. Other languages retain their existing translations and add primary v2 labels; some new explanations fall back to English.

Profile PINs and drafts are stored in app-private preferences, excluded from Android backups/device transfer. They are not protected by a separate encryption vault.
