#include "unlock_engine.h"

#include <sddl.h>
#include <wincrypt.h>
#include <algorithm>
#include <ctime>
#include <fstream>
#include <functional>
#include <sstream>

namespace pcpr {

namespace {

int64_t NowSeconds() {
    return static_cast<int64_t>(std::time(nullptr));
}

std::string ErrorJson(const std::string& code, const std::string& message, int status = 400) {
    JsonWriter w;
    w.Bool("ok", false).Str("error", code).Str("message", message).Int("status", status);
    return w.Build();
}

bool IsProviderRegisteredInSystem() {
    std::wstring cpKey = std::wstring(L"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Authentication\\Credential Providers\\") + kProviderClsidString;
    HKEY hKey = nullptr;
    if (RegOpenKeyExW(HKEY_LOCAL_MACHINE, cpKey.c_str(), 0, KEY_READ, &hKey) == ERROR_SUCCESS) {
        RegCloseKey(hKey);
        return true;
    }
    return false;
}

void WakeLockScreenDisplay() {
    SetThreadExecutionState(ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED);
    SendNotifyMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, static_cast<LPARAM>(-1));
    mouse_event(MOUSEEVENTF_MOVE, 1, 0, 0, 0);
}

bool EnsureSecureDirectory(const std::wstring& dir, bool allowTestPeer, const std::wstring& testOwnerSid) {
    CreateDirectoryW(dir.c_str(), nullptr);
    DWORD attr = GetFileAttributesW(dir.c_str());
    if (attr == INVALID_FILE_ATTRIBUTES || !(attr & FILE_ATTRIBUTE_DIRECTORY)) return false;

    std::wstring sddl = L"D:P(A;OICI;GA;;;SY)(A;OICI;GA;;;BA)(A;OICI;GA;;;IU)";
    if (allowTestPeer && !testOwnerSid.empty()) {
        sddl += L"(A;OICI;GA;;;" + testOwnerSid + L")";
    }
    PSECURITY_DESCRIPTOR sd = nullptr;
    if (ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl.c_str(), SDDL_REVISION_1, &sd, nullptr)) {
        SetFileSecurityW(dir.c_str(), DACL_SECURITY_INFORMATION, sd);
        LocalFree(sd);
    }
    return true;
}

void RunPipeServerLoop(
    const std::wstring& pipeName,
    bool systemOnly,
    const std::wstring& testOwnerSid,
    HANDLE stopEvent,
    std::atomic<bool>& running,
    std::function<std::string(const std::string&, const PeerIdentity&)> handler) {
    while (running.load()) {
        HANDLE pipe = CreateSecureServerPipe(pipeName, systemOnly, testOwnerSid);
        if (pipe == INVALID_HANDLE_VALUE) {
            if (WaitForSingleObject(stopEvent, 200) == WAIT_OBJECT_0) break;
            continue;
        }

        OVERLAPPED ov = {};
        ov.hEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        BOOL connected = ConnectNamedPipe(pipe, &ov);
        DWORD err = GetLastError();
        bool ready = false;
        if (connected) {
            ready = true;
        } else if (err == ERROR_PIPE_CONNECTED) {
            ready = true;
        } else if (err == ERROR_IO_PENDING) {
            HANDLE waits[2] = {stopEvent, ov.hEvent};
            DWORD w = WaitForMultipleObjects(2, waits, FALSE, INFINITE);
            if (w == WAIT_OBJECT_0 + 1) {
                DWORD dummy = 0;
                if (GetOverlappedResult(pipe, &ov, &dummy, FALSE)) ready = true;
            } else {
                CancelIo(pipe);
            }
        }
        CloseHandle(ov.hEvent);

        if (ready && running.load()) {
            PeerIdentity peer;
            std::string req;
            if (GetPipeClientIdentity(pipe, peer) && PipeReadMessage(pipe, req)) {
                std::string resp = handler(req, peer);
                Wipe(req);
                PipeWriteMessage(pipe, resp);
                Wipe(resp);
                FlushFileBuffers(pipe);
            }
            DisconnectNamedPipe(pipe);
        }
        CloseHandle(pipe);
    }
}

}  // namespace

UnlockEngine::UnlockEngine(EngineConfig cfg) : cfg_(std::move(cfg)) {
    stopEvent_ = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    resultEvent_ = CreateEventW(nullptr, TRUE, FALSE, nullptr);

    // Ready event signaled when a credential is available for the Credential Provider.
    std::wstring sddl = L"D:P(A;;GA;;;SY)(A;;GA;;;BA)";
    if (cfg_.allowTestPeer && !cfg_.testOwnerSid.empty()) {
        sddl += L"(A;;GA;;;" + cfg_.testOwnerSid + L")";
    }
    PSECURITY_DESCRIPTOR sd = nullptr;
    SECURITY_ATTRIBUTES sa = {sizeof(sa), nullptr, FALSE};
    if (ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl.c_str(), SDDL_REVISION_1, &sd, nullptr)) {
        sa.lpSecurityDescriptor = sd;
    }
    readyEvent_ = CreateEventW(sa.lpSecurityDescriptor ? &sa : nullptr, FALSE, FALSE, cfg_.readyEventName.c_str());
    if (!readyEvent_) {
        // Fallback to local unnamed event if Global\ namespace requires SeCreateGlobalPrivilege in user-mode tests.
        readyEvent_ = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    }
    if (sd) LocalFree(sd);
}

UnlockEngine::~UnlockEngine() {
    Stop();
    if (stopEvent_) CloseHandle(stopEvent_);
    if (readyEvent_) CloseHandle(readyEvent_);
    if (resultEvent_) CloseHandle(resultEvent_);
}

bool UnlockEngine::DpapiProtect(const Bytes& plain, Bytes& out) const {
    DATA_BLOB inBlob = {(DWORD)plain.size(), const_cast<BYTE*>(plain.data())};
    DATA_BLOB outBlob = {};
    DWORD flags = CRYPTPROTECT_UI_FORBIDDEN | CRYPTPROTECT_LOCAL_MACHINE;
    if (!CryptProtectData(&inBlob, L"PCPhoneRemoteUnlock", nullptr, nullptr, nullptr, flags, &outBlob)) {
        return false;
    }
    out.assign(outBlob.pbData, outBlob.pbData + outBlob.cbData);
    LocalFree(outBlob.pbData);
    return true;
}

bool UnlockEngine::DpapiUnprotect(const Bytes& blob, Bytes& out) const {
    if (blob.empty()) return false;
    DATA_BLOB inBlob = {(DWORD)blob.size(), const_cast<BYTE*>(blob.data())};
    DATA_BLOB outBlob = {};
    if (!CryptUnprotectData(&inBlob, nullptr, nullptr, nullptr, nullptr, CRYPTPROTECT_UI_FORBIDDEN, &outBlob)) {
        return false;
    }
    out.assign(outBlob.pbData, outBlob.pbData + outBlob.cbData);
    SecureZeroMemory(outBlob.pbData, outBlob.cbData);
    LocalFree(outBlob.pbData);
    return true;
}

bool UnlockEngine::LoadOrCreateState() {
    std::lock_guard<std::mutex> lock(mu_);
    if (cfg_.stateDir.empty()) {
        wchar_t progData[MAX_PATH] = {};
        DWORD n = GetEnvironmentVariableW(L"ProgramData", progData, MAX_PATH);
        std::wstring base = n ? std::wstring(progData) : L"C:\\ProgramData";
        CreateDirectoryW((base + L"\\PCPhoneRemote").c_str(), nullptr);
        cfg_.stateDir = base + L"\\PCPhoneRemote\\unlock";
    }
    if (!EnsureSecureDirectory(cfg_.stateDir, cfg_.allowTestPeer, cfg_.testOwnerSid)) {
        return false;
    }

    std::wstring path = cfg_.stateDir + L"\\state.json";
    std::ifstream in(path, std::ios::binary);
    if (in.good()) {
        std::ostringstream ss;
        ss << in.rdbuf();
        JsonObject obj;
        if (JsonParseFlat(ss.str(), obj)) {
            Bytes dpapiKey, rawKey;
            if (B64UrlDecode(Get(obj, "pc_ecdh_dpapi"), dpapiKey) &&
                DpapiUnprotect(dpapiKey, rawKey) &&
                pcEcdh_.ImportPrivate(rawKey)) {
                Wipe(rawKey);
                enrolled_ = (Get(obj, "enrolled") == "true");
                deviceId_ = Get(obj, "device_id");
                deviceName_ = Get(obj, "device_name");
                B64UrlDecode(Get(obj, "phone_pub"), phonePub_);
                userSid_ = Utf8ToWide(Get(obj, "user_sid"));
                qualifiedUser_ = Utf8ToWide(Get(obj, "qualified_user"));
                vaultMode_ = Get(obj, "vault_mode");
                B64UrlDecode(Get(obj, "vault_iv"), vaultIv_);
                B64UrlDecode(Get(obj, "vault_dpapi"), vaultDpapi_);
                in.close();
                if (!vaultDpapi_.empty()) {
                    SecretBytes unprotVault;
                    Bytes reprotVault;
                    if (DpapiUnprotect(vaultDpapi_, unprotVault.value) &&
                        DpapiProtect(unprotVault.value, reprotVault)) {
                        vaultDpapi_ = std::move(reprotVault);
                    }
                }
                SaveStateLocked();
                return true;
            }
            Wipe(rawKey);
        }
    }

    if (!pcEcdh_.Generate()) return false;
    enrolled_ = false;
    return SaveStateLocked();
}

bool UnlockEngine::SaveStateLocked() {
    SecretBytes rawKey;
    Bytes dpapiKey;
    if (!pcEcdh_.ExportPrivate(rawKey.value) || !DpapiProtect(rawKey.value, dpapiKey)) {
        return false;
    }
    JsonWriter w;
    w.Bool("enrolled", enrolled_)
     .Str("pc_ecdh_dpapi", B64UrlEncode(dpapiKey))
     .Str("device_id", deviceId_)
     .Str("device_name", deviceName_)
     .Str("phone_pub", B64UrlEncode(phonePub_))
     .Str("user_sid", WideToUtf8(userSid_))
     .Str("qualified_user", WideToUtf8(qualifiedUser_))
     .Str("vault_mode", vaultMode_)
     .Str("vault_iv", B64UrlEncode(vaultIv_))
     .Str("vault_dpapi", B64UrlEncode(vaultDpapi_));

    std::wstring tmpPath = cfg_.stateDir + L"\\state.json.tmp";
    std::wstring finalPath = cfg_.stateDir + L"\\state.json";
    {
        std::ofstream out(tmpPath, std::ios::binary | std::ios::trunc);
        if (!out.good()) return false;
        std::string text = w.Build();
        out.write(text.data(), (std::streamsize)text.size());
        out.flush();
        if (!out.good()) return false;
    }
    return MoveFileExW(tmpPath.c_str(), finalPath.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != FALSE;
}

bool UnlockEngine::Start() {
    if (running_.load()) return true;
    if (!LoadOrCreateState()) return false;
    ResetEvent(stopEvent_);
    running_.store(true);
    controlThread_ = std::thread([this]() { ControlLoop(); });
    providerThread_ = std::thread([this]() { ProviderLoop(); });
    return true;
}

void UnlockEngine::Stop() {
    if (!running_.exchange(false)) return;
    SetEvent(stopEvent_);
    SetEvent(resultEvent_);
    if (controlThread_.joinable()) controlThread_.join();
    if (providerThread_.joinable()) providerThread_.join();
    std::lock_guard<std::mutex> lock(mu_);
    Wipe(pendingCred_.password);
}

void UnlockEngine::ControlLoop() {
    RunPipeServerLoop(
        cfg_.controlPipe,
        /*systemOnly=*/false,
        cfg_.testOwnerSid,
        stopEvent_,
        running_,
        [this](const std::string& req, const PeerIdentity& peer) {
            return HandleControlRequest(req, peer);
        });
}

void UnlockEngine::ProviderLoop() {
    RunPipeServerLoop(
        cfg_.providerPipe,
        /*systemOnly=*/true,
        cfg_.allowTestPeer ? cfg_.testOwnerSid : L"",
        stopEvent_,
        running_,
        [this](const std::string& req, const PeerIdentity& peer) {
            return HandleProviderRequest(req, peer);
        });
}

bool UnlockEngine::IsRateLimitedLocked(int64_t now, int64_t& retryAfterOut) {
    retryAfterOut = 0;
    failures_.erase(
        std::remove_if(failures_.begin(), failures_.end(), [now](int64_t t) { return t <= now - 300; }),
        failures_.end());
    if (lockoutUntil_ > now) {
        retryAfterOut = lockoutUntil_ - now;
        return true;
    }
    if (failures_.size() >= 5) {
        lockoutUntil_ = now + 60;
        retryAfterOut = 60;
        return true;
    }
    return false;
}

void UnlockEngine::RecordFailureLocked(int64_t now) {
    failures_.push_back(now);
    if (failures_.size() >= 5) {
        lockoutUntil_ = now + 60;
    }
}

std::string UnlockEngine::HandleControlRequest(const std::string& jsonReq, const PeerIdentity& peer) {
    JsonObject req;
    if (!JsonParseFlat(jsonReq, req)) {
        return ErrorJson("bad_json", "Invalid JSON object", 400);
    }
    std::string op = Get(req, "op");
    int64_t now = NowSeconds();

    // Status query (safe metadata only, never exposes secrets).
    if (op == "enroll.status" || op == "unlock.status") {
        std::lock_guard<std::mutex> lock(mu_);
        Bytes pub = pcEcdh_.PublicPoint();
        Bytes fp = Sha256(pub);
        JsonWriter w;
        w.Bool("ok", true)
         .Bool("enrolled", enrolled_)
         .Str("device_id", deviceId_)
         .Str("device_name", deviceName_)
         .Str("user_sid", WideToUtf8(userSid_))
         .Str("qualified_user", WideToUtf8(qualifiedUser_))
         .Str("vault_mode", vaultMode_)
         .Str("pc_pub", B64UrlEncode(pub))
         .Str("pc_pub_fp", B64UrlEncode(fp))
         .Bool("provider_installed", IsProviderRegisteredInSystem())
         .Bool("locked", IsConsoleSessionLocked());
        return w.Build();
    }

    if (op == "account.detect") {
        std::wstring targetUser = Utf8ToWide(Get(req, "username"));
        if (targetUser.empty()) {
            targetUser = peer.accountName;
        }
        std::wstring msaProv, msaPrinc, msaSid;
        bool isMsa = ResolveInternetIdentity(targetUser, msaProv, msaPrinc, msaSid);
        JsonWriter w;
        w.Bool("ok", true)
         .Str("peer_account", WideToUtf8(peer.accountName))
         .Str("peer_sid", WideToUtf8(peer.userSid))
         .Bool("is_msa", isMsa)
         .Str("msa_provider", WideToUtf8(msaProv))
         .Str("msa_principal", WideToUtf8(msaPrinc));
        return w.Build();
    }

    // Physical PC enrollment initiation: requires local interactive console user or administrator.
    if (op == "enroll.begin") {
        DWORD activeConsole = WTSGetActiveConsoleSessionId();
        bool onUnlockedConsole = (peer.sessionId == activeConsole && !peer.userSid.empty() && !IsConsoleSessionLocked());
        bool allowedCaller = peer.isSystem || peer.isAdmin ||
                             (peer.sessionId == activeConsole && !peer.userSid.empty()) ||
                             (cfg_.allowTestPeer && peer.userSid == cfg_.testOwnerSid);
        if (!allowedCaller) {
            return ErrorJson("forbidden", "Enrollment requires physical console access on the PC", 403);
        }

        std::wstring username = Utf8ToWide(Get(req, "username"));
        std::wstring domain = Utf8ToWide(Get(req, "domain"));
        std::wstring password = Utf8ToWide(Get(req, "password"));
        std::string mode = Get(req, "mode");
        bool skipVerify = (Get(req, "skip_verify") == "true");
        if (mode.empty()) mode = "split_key";
        if (mode != "split_key" && mode != "password_only") {
            Wipe(password);
            return ErrorJson("bad_mode", "Mode must be split_key or password_only", 400);
        }
        if (username.empty() || password.empty()) {
            Wipe(password);
            return ErrorJson("missing_credentials", "Введите имя пользователя и пароль учётной записи Windows", 400);
        }

        std::wstring verifiedSid;
        std::wstring canonicalUser;
        DWORD winErr = 0;
        if (cfg_.allowSyntheticLogon && !Get(req, "test_sid").empty()) {
            verifiedSid = Utf8ToWide(Get(req, "test_sid"));
            canonicalUser = (domain.empty() ? L"TESTPC" : domain) + L"\\" + username;
        } else if (skipVerify && onUnlockedConsole && !peer.userSid.empty()) {
            // Active unlocked console user explicitly saving their Microsoft Account password when
            // Windows 11 hasn't cached the MSA password hash in local SAM yet (PIN-only history).
            // Strictly bound to the caller's own console SID!
            verifiedSid = peer.userSid;
            std::wstring msaProv, msaPrinc, msaSid;
            if (ResolveInternetIdentity(peer.accountName, msaProv, msaPrinc, msaSid)) {
                canonicalUser = msaProv + L"\\" + msaPrinc;
            } else {
                canonicalUser = peer.accountName.empty()
                                    ? (domain.empty() ? username : (domain + L"\\" + username))
                                    : peer.accountName;
            }
        } else {
            if (!VerifyWindowsPasswordInteractive(domain, username, password, verifiedSid, winErr, &canonicalUser)) {
                bool looksLikeNumericPin = (password.size() >= 4 && password.size() <= 10 &&
                                            std::all_of(password.begin(), password.end(),
                                                        [](wchar_t c) { return c >= L'0' && c <= L'9'; }));
                std::wstring msaProv, msaPrinc, msaSid;
                bool isMsa = ResolveInternetIdentity(username, msaProv, msaPrinc, msaSid) ||
                             ResolveInternetIdentity(peer.accountName, msaProv, msaPrinc, msaSid);
                Wipe(password);

                if (looksLikeNumericPin && winErr == ERROR_LOGON_FAILURE) {
                    std::string msaHint = isMsa ? (" (" + WideToUtf8(msaPrinc) + ")") : "";
                    return ErrorJson(
                        "pin_not_password",
                        "Вы ввели цифровой PIN-код Windows Hello, а не пароль! "
                        "В Windows короткий PIN-код зашифрован внутри чипа TPM и не принимается системой как пароль (ошибка 1326). "
                        "Введите здесь ПАРОЛЬ от вашей учётной записи Microsoft/Windows" + msaHint +
                        ", а свой короткий PIN-код укажите в поле «PIN для телефона» ниже!",
                        403);
                }
                if (isMsa && winErr == ERROR_LOGON_FAILURE) {
                    return ErrorJson(
                        "msa_auth_failed",
                        "Windows отклонила пароль для учётной записи Microsoft (" + WideToUtf8(msaPrinc) + ", код 1326). "
                        "Убедитесь, что вводите именно пароль от аккаунта Microsoft (а не PIN-код от экрана Windows). "
                        "Если вы никогда не входили на этот ПК по паролю Microsoft (только по PIN), поставьте галочку "
                        "«Сохранить пароль без локальной проверки кэша Windows» ниже.",
                        403);
                }
                return ErrorJson("windows_auth_failed",
                                 "Windows отклонила имя пользователя или пароль (код ошибки " + std::to_string(winErr) + ")", 403);
            }
            if (canonicalUser.empty()) {
                std::wstring queryName = domain.empty() ? username : (domain + L"\\" + username);
                std::wstring dummySid;
                if (!LookupAccountSidString(queryName, dummySid, canonicalUser)) {
                    canonicalUser = queryName;
                }
            }
        }

        SecretBytes splitKey(RandomBytes(32));
        Bytes vaultIv = RandomBytes(kGcmIvSize);
        Bytes vaultDpapi;
        if (mode == "split_key") {
            std::string pwUtf8 = WideToUtf8(password);
            SecretBytes pwBytes(ToBytes(pwUtf8));
            Wipe(pwUtf8);
            std::string aadStr = "pcpr-vault-v1|" + WideToUtf8(verifiedSid);
            Bytes ct;
            if (!AesGcmEncrypt(splitKey.value, vaultIv, ToBytes(aadStr), pwBytes.value, ct) ||
                !DpapiProtect(ct, vaultDpapi)) {
                Wipe(password);
                return ErrorJson("crypto_error", "Could not seal Windows credential vault", 500);
            }
            Wipe(ct);
        }
        Wipe(password);

        Bytes tokenBytes = RandomBytes(32);
        std::string tokenB64 = B64UrlEncode(tokenBytes);
        std::string kB64 = (mode == "split_key") ? B64UrlEncode(splitKey.value) : "";

        std::lock_guard<std::mutex> lock(mu_);
        pendingEnroll_ = PendingEnrollment{
            tokenB64,
            verifiedSid,
            canonicalUser,
            mode,
            vaultIv,
            vaultDpapi,
            now + 300
        };
        Bytes pub = pcEcdh_.PublicPoint();
        Bytes fp = Sha256(pub);

        JsonWriter w;
        w.Bool("ok", true)
         .Str("enroll_token", tokenB64)
         .Str("split_key", kB64)
         .Str("vault_mode", mode)
         .Str("user_sid", WideToUtf8(verifiedSid))
         .Str("qualified_user", WideToUtf8(canonicalUser))
         .Str("pc_pub", B64UrlEncode(pub))
         .Str("pc_pub_fp", B64UrlEncode(fp))
         .Int("expires_at", now + 300);
        Wipe(kB64);
        return w.Build();
    }

    // Enrollment completion from the phone (proving possession of enroll_token and registering phone_pub).
    if (op == "enroll.complete") {
        std::lock_guard<std::mutex> lock(mu_);
        if (pendingEnroll_.token.empty() || pendingEnroll_.expiresAt < now) {
            pendingEnroll_ = PendingEnrollment{};
            return ErrorJson("enroll_expired", "Enrollment token expired; generate a new QR code on the PC", 410);
        }
        std::string token = Get(req, "enroll_token");
        std::string devId = Get(req, "device_id");
        std::string devName = Get(req, "device_name");
        std::string phonePubB64 = Get(req, "phone_pub");
        std::string sigB64 = Get(req, "signature");

        Bytes tokenA( token.begin(), token.end() );
        Bytes tokenB( pendingEnroll_.token.begin(), pendingEnroll_.token.end() );
        if (!ConstantTimeEqual(tokenA, tokenB)) {
            RecordFailureLocked(now);
            return ErrorJson("invalid_token", "Invalid enrollment token", 403);
        }
        if (devId.size() < 6 || devId.size() > 64) {
            return ErrorJson("invalid_device_id", "Invalid phone device_id", 400);
        }
        Bytes phonePub, sig;
        if (!B64UrlDecode(phonePubB64, phonePub) || phonePub.size() != kPointSize ||
            !B64UrlDecode(sigB64, sig)) {
            return ErrorJson("invalid_key", "Invalid phone public key or signature encoding", 400);
        }

        Bytes pub = pcEcdh_.PublicPoint();
        std::string fpB64 = B64UrlEncode(Sha256(pub));
        std::string sidUtf8 = WideToUtf8(pendingEnroll_.userSid);
        std::string transcript = "pcpr-enroll-v1\n" + token + "\n" + fpB64 + "\n" + sidUtf8 + "\n" + devId + "\n" + phonePubB64;
        if (!EcdsaVerify(phonePub, ToBytes(transcript), sig)) {
            RecordFailureLocked(now);
            return ErrorJson("invalid_signature", "Phone enrollment signature verification failed", 403);
        }

        enrolled_ = true;
        deviceId_ = devId;
        deviceName_ = devName.empty() ? "Android Phone" : devName.substr(0, 64);
        phonePub_ = phonePub;
        userSid_ = pendingEnroll_.userSid;
        qualifiedUser_ = pendingEnroll_.qualifiedUser;
        vaultMode_ = pendingEnroll_.vaultMode;
        vaultIv_ = pendingEnroll_.vaultIv;
        vaultDpapi_ = pendingEnroll_.vaultDpapi;
        pendingEnroll_ = PendingEnrollment{};
        challenges_.clear();
        failures_.clear();
        lockoutUntil_ = 0;

        if (!SaveStateLocked()) {
            return ErrorJson("save_failed", "Could not persist enrollment state", 500);
        }

        JsonWriter w;
        w.Bool("ok", true)
         .Bool("enrolled", true)
         .Str("device_id", deviceId_)
         .Str("user_sid", sidUtf8)
         .Str("qualified_user", WideToUtf8(qualifiedUser_))
         .Str("vault_mode", vaultMode_)
         .Str("pc_pub", B64UrlEncode(pub))
         .Str("pc_pub_fp", fpB64);
        return w.Build();
    }

    if (op == "enroll.revoke") {
        DWORD activeConsole = WTSGetActiveConsoleSessionId();
        bool allowedCaller = peer.isSystem || peer.isAdmin ||
                             (peer.sessionId == activeConsole && !peer.userSid.empty()) ||
                             (cfg_.allowTestPeer && peer.userSid == cfg_.testOwnerSid);
        if (!allowedCaller) {
            return ErrorJson("forbidden", "Revocation requires local console access", 403);
        }
        std::lock_guard<std::mutex> lock(mu_);
        enrolled_ = false;
        deviceId_.clear();
        deviceName_.clear();
        phonePub_.clear();
        userSid_.clear();
        qualifiedUser_.clear();
        vaultMode_.clear();
        vaultIv_.clear();
        vaultDpapi_.clear();
        pendingEnroll_ = PendingEnrollment{};
        challenges_.clear();
        Wipe(pendingCred_.password);
        SaveStateLocked();
        JsonWriter w;
        w.Bool("ok", true).Bool("enrolled", false);
        return w.Build();
    }

    // Step 1 of unlock: issue a single-use, 30-second challenge bound to the enrolled SID.
    if (op == "unlock.challenge") {
        std::lock_guard<std::mutex> lock(mu_);
        int64_t retryAfter = 0;
        if (IsRateLimitedLocked(now, retryAfter)) {
            return ErrorJson("rate_limited", "Too many failed unlock attempts. Try again in " + std::to_string(retryAfter) + "s", 429);
        }
        if (!enrolled_ || userSid_.empty() || phonePub_.size() != kPointSize) {
            return ErrorJson("not_enrolled", "Phone unlock is not configured on this PC yet", 412);
        }

        // Clean up expired challenges and old nonces.
        for (auto it = challenges_.begin(); it != challenges_.end();) {
            if (it->second.expiresAt <= now) it = challenges_.erase(it);
            else ++it;
        }
        for (auto it = usedNonces_.begin(); it != usedNonces_.end();) {
            if (it->second <= now - 300) it = usedNonces_.erase(it);
            else ++it;
        }
        if (challenges_.size() >= 16) {
            challenges_.erase(challenges_.begin());
        }

        Challenge ch;
        ch.id = B64UrlEncode(RandomBytes(16));
        ch.nonce = RandomBytes(32);
        ch.expiresAt = now + 30;
        std::string nonceB64 = B64UrlEncode(ch.nonce);
        challenges_[ch.id] = ch;

        Bytes pub = pcEcdh_.PublicPoint();
        Bytes fp = Sha256(pub);
        JsonWriter w;
        w.Bool("ok", true)
         .Str("challenge_id", ch.id)
         .Str("nonce", nonceB64)
         .Int("expires_at", ch.expiresAt)
         .Str("user_sid", WideToUtf8(userSid_))
         .Str("qualified_user", WideToUtf8(qualifiedUser_))
         .Str("vault_mode", vaultMode_)
         .Str("pc_pub", B64UrlEncode(pub))
         .Str("pc_pub_fp", B64UrlEncode(fp))
         .Bool("provider_installed", IsProviderRegisteredInSystem())
         .Bool("locked", IsConsoleSessionLocked());
        return w.Build();
    }

    // Step 2 of unlock: validate signed + E2E-encrypted unlock request, hand off to LogonUI Credential Provider,
    // and wait for Windows LSA / LogonUI ReportResult before returning success.
    if (op == "unlock.submit") {
        std::string attemptId;
        DWORD waitMs = 12000;
        {
            std::lock_guard<std::mutex> lock(mu_);
            int64_t retryAfter = 0;
            if (IsRateLimitedLocked(now, retryAfter)) {
                return ErrorJson("rate_limited", "Too many failed unlock attempts. Wait " + std::to_string(retryAfter) + "s", 429);
            }
            if (!enrolled_) {
                return ErrorJson("not_enrolled", "Phone unlock is not enrolled on this PC", 412);
            }

            std::string cid = Get(req, "challenge_id");
            auto it = challenges_.find(cid);
            if (it == challenges_.end()) {
                RecordFailureLocked(now);
                return ErrorJson("invalid_challenge", "Challenge is unknown or already used", 403);
            }
            Challenge ch = it->second;
            challenges_.erase(it);  // Single-use: immediately consume challenge_id!

            std::string nonceB64 = B64UrlEncode(ch.nonce);
            if (usedNonces_.count(nonceB64)) {
                RecordFailureLocked(now);
                return ErrorJson("replayed_nonce", "Replay detected", 403);
            }
            usedNonces_[nonceB64] = now;

            if (ch.expiresAt < now) {
                RecordFailureLocked(now);
                return ErrorJson("challenge_expired", "Unlock challenge expired", 410);
            }

            std::string devId = Get(req, "device_id");
            std::string reqSid = Get(req, "user_sid");
            std::string tsStr = Get(req, "timestamp");
            std::string ephPubB64 = Get(req, "eph_pub");
            std::string ivB64 = Get(req, "iv");
            std::string ctB64 = Get(req, "ciphertext");
            std::string sigB64 = Get(req, "signature");

            int64_t reqTs = 0;
            try { reqTs = std::stoll(tsStr); } catch (...) { reqTs = 0; }
            if (std::llabs(now - reqTs) > 60) {
                RecordFailureLocked(now);
                return ErrorJson("clock_skew", "Request timestamp expired or skewed", 410);
            }

            std::string expectedSidUtf8 = WideToUtf8(userSid_);
            if (devId != deviceId_ || reqSid != expectedSidUtf8) {
                RecordFailureLocked(now);
                return ErrorJson("account_mismatch", "Request does not match enrolled device or Windows user SID", 403);
            }

            // Ensure the existing console session (if any user is logged in) belongs to the enrolled SID.
            if (!cfg_.allowSyntheticLogon) {
                std::wstring activeSid = GetActiveConsoleUserSid();
                if (!activeSid.empty() && _wcsicmp(activeSid.c_str(), userSid_.c_str()) != 0) {
                    RecordFailureLocked(now);
                    return ErrorJson("wrong_session_user", "A different Windows user is active on the console session", 403);
                }
            }

            Bytes ephPub, iv, ct, sig;
            if (!B64UrlDecode(ephPubB64, ephPub) || ephPub.size() != kPointSize ||
                !B64UrlDecode(ivB64, iv) || iv.size() != kGcmIvSize ||
                !B64UrlDecode(ctB64, ct) || ct.size() <= kGcmTagSize ||
                !B64UrlDecode(sigB64, sig)) {
                RecordFailureLocked(now);
                return ErrorJson("bad_envelope", "Malformed cryptographic envelope", 400);
            }

            std::string aad =
                "pcpr-unlock-v1\n" + cid + "\n" + nonceB64 + "\n" + expectedSidUtf8 + "\n" +
                deviceId_ + "\n" + tsStr + "\n" + ephPubB64 + "\n" + ivB64;
            std::string transcript = aad + "\n" + ctB64;

            if (!EcdsaVerify(phonePub_, ToBytes(transcript), sig)) {
                RecordFailureLocked(now);
                return ErrorJson("invalid_signature", "Phone signature verification failed", 403);
            }

            SecretBytes shared;
            if (!pcEcdh_.Agree(ephPub, shared.value)) {
                RecordFailureLocked(now);
                return ErrorJson("ecdh_failed", "ECDH key agreement failed", 403);
            }

            SecretBytes encKey(HkdfSha256(shared.value, ch.nonce, "pcpr-unlock-v1|" + expectedSidUtf8 + "|" + deviceId_, 32));
            SecretBytes plainBytes;
            if (!AesGcmDecrypt(encKey.value, iv, ToBytes(aad), ct, plainBytes.value)) {
                RecordFailureLocked(now);
                return ErrorJson("decrypt_failed", "Envelope decryption failed", 403);
            }

            std::string innerStr(plainBytes.value.begin(), plainBytes.value.end());
            JsonObject inner;
            bool parsed = JsonParseFlat(innerStr, inner);
            Wipe(innerStr);
            if (!parsed) {
                RecordFailureLocked(now);
                return ErrorJson("bad_inner_json", "Invalid inner payload", 400);
            }

            std::wstring passwordWide;
            std::string directPassword = Get(inner, "password");
            std::string splitKeyB64 = Get(inner, "k");
            for (auto& kv : inner) Wipe(kv.second);

            if (!directPassword.empty()) {
                passwordWide = Utf8ToWide(directPassword);
                Wipe(directPassword);
            } else if (!splitKeyB64.empty()) {
                if (vaultMode_ != "split_key" || vaultDpapi_.empty() || vaultIv_.size() != kGcmIvSize) {
                    Wipe(splitKeyB64);
                    return ErrorJson("vault_unavailable", "Split-key vault is not configured; enter password or re-enroll", 412);
                }
                SecretBytes kBytes;
                SecretBytes vaultCt;
                SecretBytes vaultPlain;
                std::string aadStr = "pcpr-vault-v1|" + expectedSidUtf8;
                bool okVault = B64UrlDecode(splitKeyB64, kBytes.value) && kBytes.value.size() == 32 &&
                               DpapiUnprotect(vaultDpapi_, vaultCt.value) &&
                               AesGcmDecrypt(kBytes.value, vaultIv_, ToBytes(aadStr), vaultCt.value, vaultPlain.value);
                Wipe(splitKeyB64);
                if (!okVault) {
                    RecordFailureLocked(now);
                    return ErrorJson("invalid_split_key", "Split key could not unlock PC vault", 403);
                }
                std::string pwUtf8(vaultPlain.value.begin(), vaultPlain.value.end());
                passwordWide = Utf8ToWide(pwUtf8);
                Wipe(pwUtf8);
            } else {
                RecordFailureLocked(now);
                return ErrorJson("missing_secret", "Unlock payload contained neither split key nor password", 400);
            }

            if (passwordWide.empty()) {
                RecordFailureLocked(now);
                return ErrorJson("empty_password", "Resolved password is empty", 400);
            }

            if (!cfg_.allowSyntheticLogon) {
                bool providerInstalled = IsProviderRegisteredInSystem();
                if (!IsConsoleSessionLocked()) {
                    Wipe(passwordWide);
                    failures_.clear();
                    lockoutUntil_ = 0;
                    std::string msg = providerInstalled
                        ? "Ключ проверен! Сессия Windows уже разблокирована (заблокируйте ПК кнопкой «Замок» или Win+L для входа с экрана блокировки)."
                        : "Крипто-ключ телефона проверен! Чтобы входить на заблокированном экране (Win+L), нажмите в configure.bat кнопку «Установить модуль экрана блокировки (от Администратора)».";
                    JsonWriter w;
                    w.Bool("ok", true)
                     .Bool("unlocked", true)
                     .Bool("already_unlocked", true)
                     .Bool("provider_installed", providerInstalled)
                     .Str("user_sid", WideToUtf8(userSid_))
                     .Str("qualified_user", WideToUtf8(qualifiedUser_))
                     .Str("message", msg);
                    return w.Build();
                }
                if (!providerInstalled) {
                    Wipe(passwordWide);
                    return ErrorJson(
                        "provider_not_installed",
                        "Модуль экрана блокировки Windows ещё не установлен! Откройте configure.bat на ПК и нажмите кнопку «Установить модуль экрана блокировки (от Администратора)».",
                        412);
                }
                WakeLockScreenDisplay();
            }

            // Prepare single-attempt credential for PhoneUnlockProvider.dll in LogonUI.exe.
            Wipe(pendingCred_.password);
            attemptId = B64UrlEncode(RandomBytes(12));
            pendingCred_.attemptId = attemptId;
            pendingCred_.userSid = userSid_;
            pendingCred_.qualifiedUser = qualifiedUser_;
            pendingCred_.password = std::move(passwordWide);
            pendingCred_.expiresAt = now + 12;
            pendingCred_.consumed = false;

            lastResult_ = AttemptResult{};
            lastResult_.attemptId = attemptId;
            ResetEvent(resultEvent_);
            SetEvent(readyEvent_);

            if (cfg_.allowSyntheticLogon && !Get(req, "wait_ms").empty()) {
                try { waitMs = (DWORD)std::stoul(Get(req, "wait_ms")); } catch (...) {}
            }
        }

        // Wait outside the mutex for PhoneUnlockProvider.dll to acquire the credential and report Windows's result.
        WaitForSingleObject(resultEvent_, waitMs);

        std::lock_guard<std::mutex> lock(mu_);
        Wipe(pendingCred_.password);
        pendingCred_.consumed = true;
        pendingCred_.expiresAt = 0;

        if (!lastResult_.completed || lastResult_.attemptId != attemptId) {
            return ErrorJson("provider_timeout",
                             "Windows lock screen provider did not respond. Make sure the PC lock screen is awake and the Credential Provider is installed.",
                             504);
        }
        if (!lastResult_.unlocked) {
            RecordFailureLocked(NowSeconds());
            JsonWriter w;
            w.Bool("ok", false)
             .Bool("unlocked", false)
             .Str("error", lastResult_.errorCode.empty() ? "logon_failed" : lastResult_.errorCode)
             .Str("message", lastResult_.message.empty() ? "Windows rejected the sign-in attempt" : lastResult_.message)
             .Int("ntstatus", static_cast<long long>(lastResult_.ntstatus))
             .Int("substatus", static_cast<long long>(lastResult_.substatus))
             .Int("status", 403);
            return w.Build();
        }

        failures_.clear();
        lockoutUntil_ = 0;
        JsonWriter w;
        w.Bool("ok", true)
         .Bool("unlocked", true)
         .Str("user_sid", WideToUtf8(userSid_))
         .Str("qualified_user", WideToUtf8(qualifiedUser_))
         .Str("message", "Windows unlocked the console session");
        return w.Build();
    }

    return ErrorJson("unknown_op", "Unsupported operation", 400);
}

std::string UnlockEngine::HandleProviderRequest(const std::string& jsonReq, const PeerIdentity& peer) {
    // Strictly verify that the peer on the Provider pipe is LogonUI.exe running as SYSTEM
    // (or the authorized self-test process when allowTestPeer is enabled).
    bool trustedProvider = peer.isLogonUi ||
                           (cfg_.allowTestPeer && peer.pid == GetCurrentProcessId() && peer.userSid == cfg_.testOwnerSid);
    if (!trustedProvider) {
        return ErrorJson("forbidden_peer", "Provider pipe only accepts SYSTEM LogonUI.exe", 403);
    }

    JsonObject req;
    if (!JsonParseFlat(jsonReq, req)) {
        return ErrorJson("bad_json", "Invalid provider request", 400);
    }
    std::string op = Get(req, "op");
    int64_t now = NowSeconds();

    std::lock_guard<std::mutex> lock(mu_);
    if (pendingCred_.expiresAt > 0 && pendingCred_.expiresAt < now) {
        Wipe(pendingCred_.password);
        pendingCred_.expiresAt = 0;
        pendingCred_.consumed = true;
    }

    if (op == "provider.poll") {
        bool hasPending = !pendingCred_.consumed && pendingCred_.expiresAt >= now && !pendingCred_.password.empty();
        JsonWriter w;
        w.Bool("ok", true)
         .Bool("has_pending", hasPending)
         .Str("attempt_id", hasPending ? pendingCred_.attemptId : "")
         .Str("user_sid", WideToUtf8(userSid_))
         .Str("qualified_user", WideToUtf8(qualifiedUser_));
        return w.Build();
    }

    if (op == "provider.acquire") {
        std::wstring reqSid = Utf8ToWide(Get(req, "user_sid"));
        bool hasPending = !pendingCred_.consumed && pendingCred_.expiresAt >= now && !pendingCred_.password.empty();
        if (!hasPending) {
            return ErrorJson("no_pending_credential", "No active unlock credential", 404);
        }
        if (reqSid.empty() || _wcsicmp(reqSid.c_str(), pendingCred_.userSid.c_str()) != 0) {
            Wipe(pendingCred_.password);
            pendingCred_.consumed = true;
            return ErrorJson("sid_mismatch", "Credential is bound to a different Windows user SID", 403);
        }

        std::string pwUtf8 = WideToUtf8(pendingCred_.password);
        Wipe(pendingCred_.password);
        pendingCred_.consumed = true;

        JsonWriter w;
        w.Bool("ok", true)
         .Str("attempt_id", pendingCred_.attemptId)
         .Str("user_sid", WideToUtf8(pendingCred_.userSid))
         .Str("qualified_user", WideToUtf8(pendingCred_.qualifiedUser))
         .Str("password", pwUtf8);
        std::string out = w.Build();
        Wipe(pwUtf8);
        w.WipeBuffer();
        return out;
    }

    if (op == "provider.report") {
        std::string attemptId = Get(req, "attempt_id");
        uint32_t nts = 0xC0000001;
        uint32_t sub = 0;
        try { nts = static_cast<uint32_t>(std::stoul(Get(req, "ntstatus"))); } catch (...) {}
        try { sub = static_cast<uint32_t>(std::stoul(Get(req, "substatus"))); } catch (...) {}

        if (!attemptId.empty() && attemptId == lastResult_.attemptId) {
            lastResult_.completed = true;
            lastResult_.ntstatus = nts;
            lastResult_.substatus = sub;
            if (nts == 0) {
                lastResult_.unlocked = true;
                lastResult_.errorCode.clear();
                lastResult_.message = "Windows unlocked the console session";
            } else if (nts == 0xC0000234u || sub == 0xC0000234u) {
                lastResult_.unlocked = false;
                lastResult_.errorCode = "account_locked";
                lastResult_.message = "Windows account is locked out due to too many failed attempts";
            } else if (nts == 0xC000006Du) {
                lastResult_.unlocked = false;
                lastResult_.errorCode = "wrong_password";
                lastResult_.message = "Windows rejected the password (if you changed your Windows password, re-enroll on the PC)";
            } else {
                lastResult_.unlocked = false;
                lastResult_.errorCode = "logon_failed";
                lastResult_.message = "Windows sign-in failed";
            }
            SetEvent(resultEvent_);
        }
        JsonWriter w;
        w.Bool("ok", true);
        return w.Build();
    }

    return ErrorJson("unknown_provider_op", "Unsupported provider operation", 400);
}

}  // namespace pcpr
