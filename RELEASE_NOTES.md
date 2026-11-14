# PC Phone Remote 2.3.0

- Desktop control center with local-only settings, pairing QR codes, server PIN and startup management.
- Windows Setup EXE, Linux self-extracting installer and portable/source archives.
- Android QR scanning, LAN discovery, onboarding, platform-aware controls and updated app icon.
- Linux integrations for media, power, touchpad, scenes and shared data; desktop/system permissions apply.
- iPhone/iPad browser interface at /app and native SwiftUI sources.
- Disk telemetry and updated shared-folder/tray configuration.
- Fixed missing relay runtime dependencies and native binaries in release packaging.
- Corrected the Python installer's autostart call.
- PIN rotation rejects old alias codes; desktop PIN changes clear API/web sessions.
- Unavailable or failed phone biometric verification no longer counts as successful verification; manual Windows password mode remains available.

## Downloads

- PCPhoneRemote-v2.3.0.apk: Android release, signed with a development key.
- PCPhoneRemote-Setup.exe: unsigned Windows installer; requires Python.
- PCPhoneRemote-Linux-Installer.run: per-user Linux installer.
- PCPhoneRemote-Windows-v2.3.0.zip: portable Windows package and native x64 components.
- PCPhoneRemote-Relay-v2.3.0.zip: relay sources.
- PCPhoneRemote-iOS-Source-v2.3.0.zip: SwiftUI sources; requires Xcode and your signing team.
- SHA256SUMS.txt: download checksums.

Container: ghcr.io/kznkutsubyo/remote-pc-control-relay:2.3.0.

## Validation And Limits

Local verification: 22 Python tests, Android release/lint and native Windows build/self-tests. GitHub Actions additionally checks Linux tests, relay-container startup, installer shell syntax and an unsigned iOS simulator build before creating the release.

No signed IPA is distributed. Linux desktop behavior and native Windows lock-screen sign-in require testing in your environment. Native self-tests do not establish successful unlock of a physical locked Windows session.

The /app browser UI is served by the PC, not the relay API. HTTPS is required for full secure-context PWA behavior.
