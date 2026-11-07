#include "ipc.h"

#include <sddl.h>
#include <wtsapi32.h>
#include <lm.h>
#include <algorithm>
#include <vector>

#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "wtsapi32.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "netapi32.lib")

namespace pcpr {

namespace {

bool SidFromToken(HANDLE token, std::wstring& sidOut, std::wstring& accountOut, bool& isSystemOut, bool& isAdminOut) {
    sidOut.clear();
    accountOut.clear();
    isSystemOut = false;
    isAdminOut = false;

    DWORD cb = 0;
    GetTokenInformation(token, TokenUser, nullptr, 0, &cb);
    if (!cb) return false;
    Bytes buf(cb);
    if (!GetTokenInformation(token, TokenUser, buf.data(), cb, &cb)) return false;
    PSID sid = reinterpret_cast<TOKEN_USER*>(buf.data())->User.Sid;

    LPWSTR sidStr = nullptr;
    if (!ConvertSidToStringSidW(sid, &sidStr)) return false;
    sidOut = sidStr;
    LocalFree(sidStr);

    isSystemOut = IsWellKnownSid(sid, WinLocalSystemSid) != FALSE;

    BOOL member = FALSE;
    SID_IDENTIFIER_AUTHORITY ntAuth = SECURITY_NT_AUTHORITY;
    PSID adminSid = nullptr;
    if (AllocateAndInitializeSid(&ntAuth, 2, SECURITY_BUILTIN_DOMAIN_RID, DOMAIN_ALIAS_RID_ADMINS,
                                 0, 0, 0, 0, 0, 0, &adminSid)) {
        if (CheckTokenMembership(nullptr, adminSid, &member) && member) {
            isAdminOut = true;
        }
        FreeSid(adminSid);
    }

    wchar_t name[256] = {};
    wchar_t domain[256] = {};
    DWORD cchName = 256, cchDomain = 256;
    SID_NAME_USE use;
    if (LookupAccountSidW(nullptr, sid, name, &cchName, domain, &cchDomain, &use)) {
        accountOut = (domain[0] ? (std::wstring(domain) + L"\\" + name) : std::wstring(name));
    }
    return true;
}

bool InspectProcess(DWORD pid, PeerIdentity& out) {
    out = PeerIdentity{};
    out.pid = pid;
    ProcessIdToSessionId(pid, &out.sessionId);

    HANDLE proc = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!proc) return false;

    wchar_t img[MAX_PATH * 2] = {};
    DWORD cch = MAX_PATH * 2;
    if (QueryFullProcessImageNameW(proc, 0, img, &cch)) {
        out.imagePath.assign(img, cch);
    }

    HANDLE tok = nullptr;
    bool ok = false;
    if (OpenProcessToken(proc, TOKEN_QUERY, &tok)) {
        ok = SidFromToken(tok, out.userSid, out.accountName, out.isSystem, out.isAdmin);
        CloseHandle(tok);
    }
    CloseHandle(proc);
    if (!ok) return false;

    wchar_t sysDir[MAX_PATH] = {};
    if (GetSystemDirectoryW(sysDir, MAX_PATH)) {
        std::wstring expected = std::wstring(sysDir) + L"\\LogonUI.exe";
        if (_wcsicmp(out.imagePath.c_str(), expected.c_str()) == 0 && out.isSystem) {
            out.isLogonUi = true;
        }
    }
    return true;
}

bool ReadExact(HANDLE h, void* buf, DWORD len) {
    uint8_t* p = static_cast<uint8_t*>(buf);
    DWORD got = 0;
    HANDLE ev = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!ev) return false;
    while (got < len) {
        OVERLAPPED ov = {};
        ov.hEvent = ev;
        ResetEvent(ev);
        DWORD chunk = 0;
        BOOL ok = ReadFile(h, p + got, len - got, &chunk, &ov);
        if (!ok) {
            if (GetLastError() != ERROR_IO_PENDING) {
                CloseHandle(ev);
                return false;
            }
            if (WaitForSingleObject(ev, 15000) != WAIT_OBJECT_0 ||
                !GetOverlappedResult(h, &ov, &chunk, FALSE)) {
                CancelIo(h);
                CloseHandle(ev);
                return false;
            }
        }
        if (chunk == 0) {
            CloseHandle(ev);
            return false;
        }
        got += chunk;
    }
    CloseHandle(ev);
    return true;
}

bool WriteExact(HANDLE h, const void* buf, DWORD len) {
    const uint8_t* p = static_cast<const uint8_t*>(buf);
    DWORD sent = 0;
    HANDLE ev = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!ev) return false;
    while (sent < len) {
        OVERLAPPED ov = {};
        ov.hEvent = ev;
        ResetEvent(ev);
        DWORD chunk = 0;
        BOOL ok = WriteFile(h, p + sent, len - sent, &chunk, &ov);
        if (!ok) {
            if (GetLastError() != ERROR_IO_PENDING) {
                CloseHandle(ev);
                return false;
            }
            if (WaitForSingleObject(ev, 15000) != WAIT_OBJECT_0 ||
                !GetOverlappedResult(h, &ov, &chunk, FALSE)) {
                CancelIo(h);
                CloseHandle(ev);
                return false;
            }
        }
        if (chunk == 0) {
            CloseHandle(ev);
            return false;
        }
        sent += chunk;
    }
    CloseHandle(ev);
    return true;
}

}  // namespace

bool GetCurrentProcessUser(std::wstring& sidOut, std::wstring& qualifiedNameOut) {
    HANDLE tok = nullptr;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &tok)) return false;
    bool isSys = false, isAdm = false;
    bool ok = SidFromToken(tok, sidOut, qualifiedNameOut, isSys, isAdm);
    CloseHandle(tok);
    return ok;
}

bool LookupAccountSidString(const std::wstring& accountName, std::wstring& sidOut, std::wstring& canonicalDomainUserOut) {
    sidOut.clear();
    canonicalDomainUserOut.clear();
    DWORD cbSid = 0, cchDomain = 0;
    SID_NAME_USE use;
    LookupAccountNameW(nullptr, accountName.c_str(), nullptr, &cbSid, nullptr, &cchDomain, &use);
    if (!cbSid) return false;
    Bytes sidBuf(cbSid);
    std::wstring domain(cchDomain, L'\0');
    if (!LookupAccountNameW(nullptr, accountName.c_str(), sidBuf.data(), &cbSid, &domain[0], &cchDomain, &use)) {
        return false;
    }
    domain.resize(cchDomain);
    LPWSTR sidStr = nullptr;
    if (!ConvertSidToStringSidW(sidBuf.data(), &sidStr)) return false;
    sidOut = sidStr;
    LocalFree(sidStr);

    size_t slash = accountName.find(L'\\');
    std::wstring userPart = (slash == std::wstring::npos) ? accountName : accountName.substr(slash + 1);
    canonicalDomainUserOut = domain.empty() ? userPart : (domain + L"\\" + userPart);
    return true;
}

bool ResolveInternetIdentity(
    const std::wstring& localUsername,
    std::wstring& providerNameOut,
    std::wstring& principalNameOut,
    std::wstring& sidOut) {
    providerNameOut.clear();
    principalNameOut.clear();
    sidOut.clear();

    std::wstring userOnly = localUsername;
    size_t slash = userOnly.find(L'\\');
    if (slash != std::wstring::npos) {
        userOnly = userOnly.substr(slash + 1);
    }
    if (userOnly.empty() || userOnly.find(L'@') != std::wstring::npos) {
        return false;
    }

    LPBYTE buf = nullptr;
    NET_API_STATUS status = NetUserGetInfo(nullptr, userOnly.c_str(), 24, &buf);
    if (status != NERR_Success || !buf) {
        return false;
    }
    auto* info = reinterpret_cast<USER_INFO_24*>(buf);
    bool isInternet = (info->usri24_internet_identity != FALSE) &&
                      info->usri24_internet_provider_name && info->usri24_internet_provider_name[0] &&
                      info->usri24_internet_principal_name && info->usri24_internet_principal_name[0];
    if (isInternet) {
        providerNameOut = info->usri24_internet_provider_name;
        principalNameOut = info->usri24_internet_principal_name;
        if (info->usri24_user_sid) {
            LPWSTR sidStr = nullptr;
            if (ConvertSidToStringSidW(info->usri24_user_sid, &sidStr)) {
                sidOut = sidStr;
                LocalFree(sidStr);
            }
        }
    }
    NetApiBufferFree(buf);
    return isInternet;
}

bool VerifyWindowsPasswordInteractive(
    const std::wstring& domain,
    const std::wstring& username,
    const std::wstring& password,
    std::wstring& sidOut,
    DWORD& win32ErrorOut,
    std::wstring* canonicalQualifiedOut) {
    sidOut.clear();
    win32ErrorOut = 0;
    if (canonicalQualifiedOut) canonicalQualifiedOut->clear();

    std::wstring domPart = domain;
    std::wstring userPart = username;
    size_t slash = username.find(L'\\');
    if (slash != std::wstring::npos) {
        domPart = username.substr(0, slash);
        userPart = username.substr(slash + 1);
    }

    struct AuthCandidate {
        std::wstring dom;
        bool nullDomain;
        std::wstring user;
        DWORD provider;
        std::wstring qualifiedLabel;
    };
    std::vector<AuthCandidate> candidates;

    // 1. Check if userPart (or the current local console user) is linked to a Microsoft Account (USER_INFO_24).
    std::wstring msaProvider, msaPrincipal, msaSid;
    if (ResolveInternetIdentity(userPart, msaProvider, msaPrincipal, msaSid)) {
        std::wstring q = msaProvider + L"\\" + msaPrincipal;
        candidates.push_back({msaProvider, false, msaPrincipal, LOGON32_PROVIDER_DEFAULT, q});
        candidates.push_back({msaProvider, false, msaPrincipal, LOGON32_PROVIDER_WINNT50, q});
        candidates.push_back({L"", true, msaPrincipal, LOGON32_PROVIDER_DEFAULT, q});
    } else if (userPart.find(L'@') != std::wstring::npos) {
        // User typed an email address (MicrosoftAccount email or AD UPN).
        // Try MicrosoftAccount first (since consumer MSA fails if domain == nullptr!), then AD UPN (domain == nullptr).
        std::wstring msaQ = L"MicrosoftAccount\\" + userPart;
        candidates.push_back({L"MicrosoftAccount", false, userPart, LOGON32_PROVIDER_DEFAULT, msaQ});
        candidates.push_back({L"MicrosoftAccount", false, userPart, LOGON32_PROVIDER_WINNT50, msaQ});
        if (!domPart.empty() && _wcsicmp(domPart.c_str(), L"MicrosoftAccount") != 0 && domPart != L".") {
            candidates.push_back({domPart, false, userPart, LOGON32_PROVIDER_DEFAULT, domPart + L"\\" + userPart});
        }
        candidates.push_back({L"", true, userPart, LOGON32_PROVIDER_DEFAULT, userPart});
    }

    // 2. Also try standard local / domain SAM account credentials.
    std::wstring stdDom = domPart.empty() ? L"." : domPart;
    candidates.push_back({stdDom, false, userPart, LOGON32_PROVIDER_DEFAULT, L""});
    if (stdDom != L".") {
        candidates.push_back({L".", false, userPart, LOGON32_PROVIDER_DEFAULT, L""});
    }

    DWORD firstErr = 0;
    for (const auto& c : candidates) {
        HANDLE token = nullptr;
        const wchar_t* domPtr = c.nullDomain ? nullptr : c.dom.c_str();
        if (LogonUserW(c.user.c_str(), domPtr, password.c_str(),
                       LOGON32_LOGON_INTERACTIVE, c.provider, &token)) {
            std::wstring acct;
            bool isSys = false, isAdm = false;
            bool ok = SidFromToken(token, sidOut, acct, isSys, isAdm);
            CloseHandle(token);
            if (ok) {
                if (canonicalQualifiedOut) {
                    *canonicalQualifiedOut = !c.qualifiedLabel.empty() ? c.qualifiedLabel : acct;
                }
                win32ErrorOut = 0;
                return true;
            }
            firstErr = ERROR_INVALID_SID;
        } else {
            DWORD err = GetLastError();
            if (firstErr == 0 || firstErr == ERROR_NO_SUCH_LOGON_SESSION || firstErr == ERROR_INVALID_PARAMETER) {
                firstErr = err;
            }
        }
    }

    win32ErrorOut = firstErr ? firstErr : ERROR_LOGON_FAILURE;
    return false;
}

std::wstring GetActiveConsoleUserSid() {
    DWORD sessionId = WTSGetActiveConsoleSessionId();
    if (sessionId == 0xFFFFFFFF) return L"";

    // First try WTSQueryUserToken (works when running as LocalSystem).
    HANDLE userToken = nullptr;
    if (WTSQueryUserToken(sessionId, &userToken)) {
        std::wstring sid, acct;
        bool isSys = false, isAdm = false;
        SidFromToken(userToken, sid, acct, isSys, isAdm);
        CloseHandle(userToken);
        if (!sid.empty()) return sid;
    }

    // Fallback for non-SYSTEM processes: query WTSUserName + WTSDomainName on that session.
    LPWSTR user = nullptr, domain = nullptr;
    DWORD cbUser = 0, cbDomain = 0;
    std::wstring sid;
    if (WTSQuerySessionInformationW(WTS_CURRENT_SERVER_HANDLE, sessionId, WTSUserName, &user, &cbUser) &&
        WTSQuerySessionInformationW(WTS_CURRENT_SERVER_HANDLE, sessionId, WTSDomainName, &domain, &cbDomain)) {
        if (user && user[0]) {
            std::wstring qualified = (domain && domain[0]) ? (std::wstring(domain) + L"\\" + user) : std::wstring(user);
            std::wstring canon;
            LookupAccountSidString(qualified, sid, canon);
        }
    }
    if (user) WTSFreeMemory(user);
    if (domain) WTSFreeMemory(domain);
    return sid;
}

bool IsConsoleSessionLocked() {
    // Check WTS session lock state on Windows 10/11 first via WTSQuerySessionInformation(WTSSessionInfoEx).
    DWORD sessionId = WTSGetActiveConsoleSessionId();
    if (sessionId != 0xFFFFFFFF) {
        LPWSTR buf = nullptr;
        DWORD bytes = 0;
        if (WTSQuerySessionInformationW(WTS_CURRENT_SERVER_HANDLE, sessionId, WTSSessionInfoEx, &buf, &bytes) && buf && bytes >= sizeof(WTSINFOEXW)) {
            auto* info = reinterpret_cast<WTSINFOEXW*>(buf);
            if (info->Level == 1) {
                LONG flags = info->Data.WTSInfoExLevel1.SessionFlags;
                WTSFreeMemory(buf);
                if (flags == WTS_SESSIONSTATE_LOCK) return true;
                if (flags == WTS_SESSIONSTATE_UNLOCK) return false;
            } else {
                WTSFreeMemory(buf);
            }
        }
    }
    // Fallback to OpenInputDesktop / SwitchDesktop.
    HDESK desktop = OpenInputDesktop(0, FALSE, DESKTOP_SWITCHDESKTOP);
    if (!desktop) return true;
    BOOL unlocked = SwitchDesktop(desktop);
    CloseDesktop(desktop);
    return !unlocked;
}

bool GetPipeClientIdentity(HANDLE pipeServer, PeerIdentity& out) {
    ULONG pid = 0;
    if (!GetNamedPipeClientProcessId(pipeServer, &pid) || pid == 0) return false;
    return InspectProcess(pid, out);
}

bool GetPipeServerIdentity(HANDLE pipeClient, PeerIdentity& out) {
    ULONG pid = 0;
    if (!GetNamedPipeServerProcessId(pipeClient, &pid) || pid == 0) return false;
    return InspectProcess(pid, out);
}

HANDLE CreateSecureServerPipe(const std::wstring& pipeName, bool systemOnly, const std::wstring& testOwnerSid) {
    // Protected DACL:
    // - Provider pipe (systemOnly=true): ONLY LocalSystem (SY), plus testOwnerSid when running in self-test mode.
    // - Control pipe (systemOnly=false): LocalSystem (SY), Builtin Administrators (BA), Interactive Users (IU),
    //   plus testOwnerSid if provided. Network/Anonymous/Untrusted callers are denied.
    std::wstring sddl = L"D:P(A;;GA;;;SY)";
    if (!testOwnerSid.empty()) {
        sddl += L"(A;;GA;;;" + testOwnerSid + L")";
    }
    if (!systemOnly) {
        sddl += L"(A;;GA;;;BA)(A;;GRGW;;;IU)";
    }

    PSECURITY_DESCRIPTOR sd = nullptr;
    if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl.c_str(), SDDL_REVISION_1, &sd, nullptr)) {
        return INVALID_HANDLE_VALUE;
    }

    SECURITY_ATTRIBUTES sa = {};
    sa.nLength = sizeof(sa);
    sa.lpSecurityDescriptor = sd;
    sa.bInheritHandle = FALSE;

    DWORD openMode = PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED;
    DWORD pipeMode = PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS;
    HANDLE h = CreateNamedPipeW(
        pipeName.c_str(),
        openMode,
        pipeMode,
        8,
        65536,
        65536,
        5000,
        &sa);
    LocalFree(sd);
    return h;
}

bool PipeReadMessage(HANDLE pipe, std::string& out, DWORD maxBytes) {
    out.clear();
    uint32_t len = 0;
    if (!ReadExact(pipe, &len, sizeof(len))) return false;
    if (len == 0 || len > maxBytes) return false;
    out.resize(len);
    if (!ReadExact(pipe, &out[0], len)) {
        Wipe(out);
        return false;
    }
    return true;
}

bool PipeWriteMessage(HANDLE pipe, const std::string& msg) {
    if (msg.empty() || msg.size() > 65536) return false;
    uint32_t len = static_cast<uint32_t>(msg.size());
    return WriteExact(pipe, &len, sizeof(len)) && WriteExact(pipe, msg.data(), len);
}

bool PipeTransact(
    const std::wstring& pipeName,
    const std::string& requestJson,
    std::string& responseJson,
    bool requireSystemServer,
    const std::wstring& allowedServerSid,
    DWORD timeoutMs) {
    responseJson.clear();
    ULONGLONG deadline = GetTickCount64() + timeoutMs;
    int notFoundRetries = 0;
    HANDLE h = INVALID_HANDLE_VALUE;
    while (GetTickCount64() < deadline) {
        h = CreateFileW(
            pipeName.c_str(),
            GENERIC_READ | GENERIC_WRITE,
            0,
            nullptr,
            OPEN_EXISTING,
            SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION | FILE_FLAG_OVERLAPPED,
            nullptr);
        if (h != INVALID_HANDLE_VALUE) break;
        DWORD err = GetLastError();
        if (err == ERROR_PIPE_BUSY) {
            WaitNamedPipeW(pipeName.c_str(), 50);
        } else if (err == ERROR_FILE_NOT_FOUND && ++notFoundRetries <= 12) {
            Sleep(15);
        } else {
            return false;
        }
    }
    if (h == INVALID_HANDLE_VALUE) return false;

    PeerIdentity serverId;
    if (!GetPipeServerIdentity(h, serverId)) {
        CloseHandle(h);
        return false;
    }
    DWORD activeConsole = WTSGetActiveConsoleSessionId();
    bool trustedServer = serverId.isSystem || serverId.isAdmin ||
                         (activeConsole != 0xFFFFFFFF && serverId.sessionId == activeConsole && !serverId.userSid.empty()) ||
                         (!allowedServerSid.empty() && _wcsicmp(serverId.userSid.c_str(), allowedServerSid.c_str()) == 0);
    if (requireSystemServer && !trustedServer) {
        CloseHandle(h);
        return false;
    }

    bool ok = PipeWriteMessage(h, requestJson) && PipeReadMessage(h, responseJson);
    CloseHandle(h);
    return ok;
}

}  // namespace pcpr
