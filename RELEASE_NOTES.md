# PC Phone Remote 2.3.1

- Added prebuilt unsigned `arm64` physical-device iOS `.ipa` (`PCPhoneRemote-v2.3.1.ipa`) to GitHub Releases for Windows/macOS sideloading via Sideloadly, AltStore, SideStore, or TrollStore without needing a Mac.
- Fixed iOS bundle build configuration (`ASSETCATALOG_COMPILER_APPICON_NAME: AppIcon`) and preserved Wake-on-LAN `mac` parameter when opening `pcphone://add?...` links (`RemoteClient.swift`).
- Fixed broken Windows desktop and Start Menu `.lnk` shortcuts caused by PowerShell's reserved `$args` variable in `installer.py`, updated `CreateShortcuts` in `tools/build_installers.py` to update Desktop subfolder shortcuts in place, and updated `configure.bat` to launch `PCPhoneRemote.exe`.
- Multi-language (`RU`, `EN`, `UK`) flicker-free Windows installer (`PCPhoneRemote-Setup.exe`) and Linux installer (`PCPhoneRemote-Linux-Installer.run`).

## Downloads

- `PCPhoneRemote-v2.3.1.apk`: Android release, signed with a development key.
- `PCPhoneRemote-v2.3.1.ipa`: Native iOS (`arm64`) unsigned IPA for sideloading via Sideloadly, AltStore, SideStore, or TrollStore (no Mac required).
- `PCPhoneRemote-Setup.exe`: unsigned Windows installer; requires Python.
- `PCPhoneRemote-Linux-Installer.run`: per-user Linux installer.
- `PCPhoneRemote-Windows-v2.3.1.zip`: portable Windows package and native x64 components.
- `PCPhoneRemote-Relay-v2.3.1.zip`: relay sources.
- `PCPhoneRemote-iOS-Source-v2.3.1.zip`: SwiftUI sources for local Xcode signing/building.
- `SHA256SUMS.txt`: download checksums.

Container: `ghcr.io/kznkutsubyo/remote-pc-control-relay:2.3.1`.

## Validation And Limits

GitHub Actions verifies server unit tests on Windows and Linux, native Windows lock-screen build and self-tests, Android release APK build, Linux installer shell syntax, relay container startup, and the `iphoneos` `arm64` `.ipa` packaging before publishing the release.

`PCPhoneRemote-v2.3.1.ipa` is an unsigned `arm64` archive intended for sideloading (free Apple ID profiles expire every 7 days unless refreshed with AltStore/SideStore or installed with TrollStore on eligible iOS builds). For zero-install iOS usage without sideloading, scan the **iPhone / Web PWA** QR code to open `/app` in Safari and add it to the Home Screen.
