# PC Phone Remote Pro — iOS Edition

Version 2.3.0 is distributed as source, not a signed IPA. GitHub Actions checks an unsigned simulator build; physical iPhone installation requires Xcode and your signing team. Desktop-session controls still depend on the target OS and its permissions.

There are two ways to run **PC Phone Remote Pro** on iPhone and iPad:

## Option 1: Instant Mobile PWA (No Mac or Xcode Required)

The Python server (`pc-phone-remote/app.py`) serves a native-feeling iOS Progressive Web App built specifically for Safari Safe Areas:

1. Start **PC Phone Remote Pro** on your Windows or Linux PC.
2. Open Safari on your iPhone/iPad and visit:
   `http://<YOUR_PC_IP>:8765/app`
   (or scan the **iPhone / iPad Safari QR** in `installer.py`).
3. Log in once with your **Unified PIN**.
4. Tap **Share → Add to Home Screen** in Safari to install it as a standalone full-screen app with its custom icon.

The browser UI is served by the PC, not the relay API. HTTPS is required for service workers and full secure-context PWA behavior; plain LAN HTTP supports the basic page. Native iOS clients can use a configured relay URL.

## Option 2: Native SwiftUI iOS App (`pc-phone-remote-ios/`)

Includes hardware-accelerated UI, Face ID / Touch ID authentication (`LocalAuthentication` + Keychain), CryptoKit P-256 E2E Windows Lock Screen Unlock (`unlock.challenge` / `unlock.submit`), Linux 1-tap session unlock (`unlock.linux`), LAN UDP/HTTP PC auto-discovery, Touchpad, Stream Deck, File Transfer, and Wake-on-LAN.

### Build on macOS with XcodeGen

```bash
brew install xcodegen
cd pc-phone-remote-ios
xcodegen generate
open PCPhoneRemote.xcodeproj
```

1. Select your Apple Developer signing team in **Signing & Capabilities**.
2. Build and run on your iPhone/iPad (iOS 16.0+).
3. On first launch, tap **Auto-Find PC on Wi-Fi** or open a `pcphone://add?...` / `pcphone://enroll?...` link.
