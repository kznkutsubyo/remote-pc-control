# Native Windows Unlock: Credential Provider v2 & Service

Status: **implemented and verified via automated native self-test (`PhoneUnlockSelfTest.exe`)**. Not registered in the host's `HKLM\...\Credential Providers` by default (`WindowsLogonModified = False`); validate in a Windows VM snapshot before running `install-unlock.ps1` on a primary PC.

## Architecture

1. **`PhoneUnlockProvider.dll`** (`src/provider/provider.cpp`)
   - Native Windows Credential Provider v2 (`ICredentialProvider`, `ICredentialProviderSetUserArray`, `ICredentialProviderCredential2`) built on Microsoft's Credential Provider v2 sample architecture.
   - Retains all standard Windows password/PIN/Hello providers and never disables system policies.
   - Binds each tile to the specific user SID (`ICredentialProviderUser::GetSid`) and packs credentials with `CredProtectW` + `KERB_INTERACTIVE_UNLOCK_LOGON` (`KerbWorkstationUnlockLogon` / `KerbInteractiveLogon`).
   - Reports real Windows LSA authentication outcomes back to the service through `ICredentialProviderCredential::ReportResult(ntsStatus, ntsSubstatus)`.

2. **`PhoneUnlockService.exe`** (`src/service/unlock_engine.cpp`, `src/service/main.cpp`)
   - Runs as `NT AUTHORITY\LocalSystem` (or `--console` during development/tests).
   - **Split-Key Encrypted Vault (`split_key`) & Direct E2E Password Mode (`password_only`)**:
     - During physical PC enrollment (`enroll.begin`), Windows verifies the account password via `LogonUserW` and resolves the user's exact `SID`.
     - In `split_key` mode, the password is encrypted with a fresh 256-bit AES-GCM key `K` (`aad = "pcpr-vault-v1|" + user_sid`) and wrapped with `CryptProtectData(CRYPTPROTECT_LOCAL_MACHINE)`. `K` is delivered once in the local enrollment QR/code to the phone's hardware-backed Android Keystore and immediately wiped from PC memory.
     - Neither the PC disk nor the phone alone holds the plaintext password.
   - **End-to-End Encrypted, Signed Unlock Protocol**:
     - Every unlock requires a single-use 30-second challenge (`unlock.challenge`).
     - The phone verifies the pinned PC static ECDH P-256 public key fingerprint (`pc_pub_fp`), performs ephemeral ECDH P-256 + `HKDF-SHA256` + `AES-256-GCM`, and signs the full transcript (`challenge_id`, `nonce`, `user_sid`, `device_id`, `timestamp`, `eph_pub`, `iv`, `ciphertext`) with its enrolled Android Keystore ECDSA P-256 key.
     - Plain HTTP (`app.py`) and the remote relay (`relay_server.py`) only transport opaque E2E ciphertext.
   - **Strict Named-Pipe ACLs & Peer Verification**:
     - Provider pipe (`\\.\pipe\PCPhoneRemoteUnlockProvider`): DACL `D:P(A;;GA;;;SY)` (LocalSystem only) + process verification (`%SystemRoot%\System32\LogonUI.exe` running as `SYSTEM`).
     - Control pipe (`\\.\pipe\PCPhoneRemoteUnlockControl`): DACL restricting access to `SYSTEM`, `Administrators`, and interactive console users.

## Build & Self-Test

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File windows-unlock\build.ps1 -RunTests
powershell -NoProfile -ExecutionPolicy Bypass -File windows-unlock\check-environment.ps1
```

## References

- [Windows Credential Providers](https://learn.microsoft.com/en-us/windows/win32/secauthn/credential-providers-in-windows)
- [Microsoft Credential Provider samples](https://github.com/microsoft/Windows-classic-samples/tree/main/Samples/CredentialProvider)
