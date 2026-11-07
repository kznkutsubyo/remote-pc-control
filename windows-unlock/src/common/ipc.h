// Secure named-pipe IPC with explicit Windows ACLs and peer identity verification.
#pragma once

#include "util.h"

namespace pcpr {

constexpr const wchar_t* kControlPipeName  = L"\\\\.\\pipe\\PCPhoneRemoteUnlockControl";
constexpr const wchar_t* kProviderPipeName = L"\\\\.\\pipe\\PCPhoneRemoteUnlockProvider";
constexpr const wchar_t* kReadyEventName   = L"Global\\PCPhoneRemoteUnlockReady";

// Provider CLSID: {D7F4C9E2-54C9-4E6D-9B0C-48E71F6A8C21}
// Never conflicts with built-in Windows credential providers.
constexpr const wchar_t* kProviderClsidString = L"{D7F4C9E2-54C9-4E6D-9B0C-48E71F6A8C21}";

struct PeerIdentity {
    DWORD pid = 0;
    DWORD sessionId = 0;
    std::wstring userSid;
    std::wstring accountName;   // DOMAIN\User
    std::wstring imagePath;
    bool isSystem = false;
    bool isAdmin = false;
    bool isLogonUi = false;
};

// Queries the current process user SID and DOMAIN\Username.
bool GetCurrentProcessUser(std::wstring& sidOut, std::wstring& qualifiedNameOut);

// Resolves a DOMAIN\Username or username to its SID string (S-1-5-...).
bool LookupAccountSidString(const std::wstring& accountName, std::wstring& sidOut, std::wstring& canonicalDomainUserOut);

// Resolves a local account's connected internet identity (e.g., MicrosoftAccount\user@example.com) if present.
bool ResolveInternetIdentity(
    const std::wstring& localUsername,
    std::wstring& providerNameOut,
    std::wstring& principalNameOut,
    std::wstring& sidOut);

// Validates a local or Microsoft Account Windows password using LogonUserW (for interactive enrollment check).
bool VerifyWindowsPasswordInteractive(
    const std::wstring& domain,
    const std::wstring& username,
    const std::wstring& password,
    std::wstring& sidOut,
    DWORD& win32ErrorOut,
    std::wstring* canonicalQualifiedOut = nullptr);

// Returns the SID of the user owning the active console session (WTSGetActiveConsoleSessionId + WTSQueryUserToken),
// or empty string if no user is logged into the console session.
std::wstring GetActiveConsoleUserSid();

// Returns true if the interactive console desktop is currently locked (LogonUI / Winlogon desktop active).
bool IsConsoleSessionLocked();

// Inspects the connected client of a named pipe server handle.
bool GetPipeClientIdentity(HANDLE pipeServer, PeerIdentity& out);

// Inspects the server of a named pipe client handle.
bool GetPipeServerIdentity(HANDLE pipeClient, PeerIdentity& out);

// Creates a single-instance or multi-instance server pipe handle with an explicit SDDL DACL.
// If systemOnly is true, DACL is D:P(A;;GA;;;SY) (only LocalSystem).
// If testOwnerSid is non-empty, DACL grants access only to that SID and LocalSystem.
HANDLE CreateSecureServerPipe(const std::wstring& pipeName, bool systemOnly, const std::wstring& testOwnerSid = L"");

// Reads/writes a length-prefixed (uint32 LE, <= 65536) UTF-8 message on a synchronous pipe handle.
bool PipeReadMessage(HANDLE pipe, std::string& out, DWORD maxBytes = 65536);
bool PipeWriteMessage(HANDLE pipe, const std::string& msg);

// Client helper: connects to pipeName, optionally requiring the server to be LocalSystem (or testOwnerSid),
// sends requestJson, reads responseJson, and wipes both buffers on destruction if requested.
bool PipeTransact(
    const std::wstring& pipeName,
    const std::string& requestJson,
    std::string& responseJson,
    bool requireSystemServer = false,
    const std::wstring& allowedServerSid = L"",
    DWORD timeoutMs = 15000);

}  // namespace pcpr
