# PC Phone Remote 2.2

- Native Android interface rebuilt with Kotlin and Jetpack Compose.
- Device profiles, configurable appearance, media controls, shared files and text.
- Desktop setup form and optional relay for outside-network access.
- Native Windows credential provider and service, with encrypted phone enrollment and unlock requests.

## Downloads

- `PCPhoneRemote-v2.2.apk`: manually installable Android app, signed with the development key. Not a store-signed production release.
- `PCPhoneRemote-Windows-v2.2.zip`: Python server, configuration tools, Windows x64 unlock components and install/uninstall scripts. Python and the dependencies in requirements.txt are required.
- `PCPhoneRemote-Relay-v2.2.zip`: relay source distribution.
- `SHA256SUMS.txt`: download checksums.

Native unlock passes automated self-tests; a real Windows lock-screen sign-in has not been verified in a disposable VM. Keep a recovery route and validate on a test machine before registering the optional credential provider.

Relay container: `ghcr.io/kznkutsubyo/remote-pc-control-relay:2.2.0` (published by the tag workflow). Configure RELAY_PIN and a random RELAY_AGENT_TOKEN of at least 24 characters, and put HTTPS in front of the service. One relay instance serves one PC.

Validation: Python server tests, Android release build, native Windows build and native self-tests.
