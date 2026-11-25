# PC Phone Remote Pro — iOS Edition

Version **2.4.0** provides three ways to run **PC Phone Remote Pro** on iPhone and iPad (iOS 16.0+):
- **Safari PWA** at `http://<YOUR_PC_IP>:8765/app` (or HTTPS with optional local TLS certificate)
- **Prebuilt Unsigned `.ipa`** (`PCPhoneRemote-v2.4.0.ipa`) in [GitHub Releases](https://github.com/kznkutsubyo/remote-pc-control/releases/latest) for sideloading from Windows or macOS
- **Native SwiftUI Source** (`pc-phone-remote-ios/`) for building locally with Xcode

Includes built-in **QR Code Camera Scanner**, **Siri Shortcuts (`AppIntents`)**, **Live Screen View & Tap**, **Live Keyboard & Hotkeys**, **Real OS Clipboard Sync**, **Audio Output & App Volume Mixer**, **Display Brightness & Screen Off**, **Custom Studio Pro Buttons**, and **Process Manager**!

> **Note:** Apple does not permit installing apps directly from Safari without an App Store listing or provisioning signature. Because the prebuilt `.ipa` is unsigned, sideloading it onto a physical device requires signing with your Apple ID via a sideloading tool (free personal Apple IDs require re-signing every 7 days unless automatic Wi-Fi refresh is used).

---

## Option 1: Instant Mobile PWA (No Mac or Sideloading Required)

The Python server (`pc-phone-remote/app.py`) serves an iOS Progressive Web App tailored for Safari Safe Areas:

1. Start **PC Phone Remote** on your Windows or Linux PC and open the Desktop Control Center (`http://127.0.0.1:8765/desktop`).
2. Switch to **QR Pairing → iPhone / Web PWA** and scan the QR code with the standard iPhone Camera app (or open `http://<YOUR_PC_IP>:8765/app` in Safari).
3. Sign in with your **Unified PIN** (auto-filled if scanned from QR).
4. Tap **Share → Add to Home Screen** in Safari to install it as a full-screen home-screen app.

The browser UI is served directly by the PC, not the relay API. HTTPS is required for service workers and full secure-context PWA behavior; plain LAN HTTP supports the interactive page.

---

## Option 2: Prebuilt Unsigned `.ipa` (Windows / macOS Sideloading — No Mac Required)

Includes native SwiftUI performance, Face ID / Touch ID (`LocalAuthentication` + Keychain), CryptoKit P-256 E2E Windows Lock Screen Unlock (`unlock.challenge` / `unlock.submit`), Linux 1-tap session unlock (`unlock.linux`), UDP/HTTP LAN discovery, Touchpad, Stream Deck, File Transfer, and Wake-on-LAN.

1. Download **`PCPhoneRemote-v2.3.1.ipa`** from [GitHub Releases](https://github.com/kznkutsubyo/remote-pc-control/releases/latest).
2. Install onto your iPhone/iPad using one of these tools:
   - **Sideloadly (Windows / macOS, easiest from Windows):**
     1. Connect your iPhone to Windows via USB and tap **Trust This Computer** on the phone.
     2. Open Sideloadly, drag **`PCPhoneRemote-v2.3.1.ipa`** into it, enter your Apple ID, and click **Start**.
     3. On your iPhone go to **Settings → General → VPN & Device Management**, select your Apple ID profile, and tap **Trust**.
     4. On iOS 16+, enable **Settings → Privacy & Security → Developer Mode** if prompted, then launch **PC Remote**.
   - **AltStore / SideStore:** Download the `.ipa` on your PC or phone, import it into AltStore/SideStore, and let AltStore/SideStore handle 7-day background Wi-Fi re-signing automatically.
   - **TrollStore (supported devices only, iOS 14.0–16.6.1 / 17.0):** Share **`PCPhoneRemote-v2.3.1.ipa`** to TrollStore for permanent installation without 7-day expiration.
3. On first launch in the app, tap **Auto-Find PC on Wi-Fi** (UDP 8766 discovery) or add your PC via `pcphone://add?...` / `pcphone://enroll?...`.

---

## Option 3: Build from Source with Xcode (macOS)

```bash
brew install xcodegen
cd pc-phone-remote-ios
xcodegen generate
open PCPhoneRemote.xcodeproj
```

1. Select your Apple Developer signing team in **Signing & Capabilities**.
2. Build and run on your iPhone/iPad (`iOS 16.0+`).
3. On first launch, tap **Auto-Find PC on Wi-Fi** or open a `pcphone://add?...` / `pcphone://enroll?...` link.
