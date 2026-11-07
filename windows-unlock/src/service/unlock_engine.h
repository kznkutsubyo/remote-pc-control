// Core state machine and pipe servers for the Windows Phone Unlock Service.
#pragma once

#include "../common/crypto.h"
#include "../common/ipc.h"
#include "../common/util.h"

#include <atomic>
#include <mutex>
#include <thread>

namespace pcpr {

struct EngineConfig {
    std::wstring stateDir;
    std::wstring controlPipe = kControlPipeName;
    std::wstring providerPipe = kProviderPipeName;
    std::wstring readyEventName = kReadyEventName;
    // Used ONLY in automated self-tests:
    bool allowTestPeer = false;
    bool allowSyntheticLogon = false;
    std::wstring testOwnerSid;
};

class UnlockEngine {
public:
    explicit UnlockEngine(EngineConfig cfg);
    ~UnlockEngine();

    bool Start();
    void Stop();

    // Direct dispatch helpers (also exposed over the named pipes).
    std::string HandleControlRequest(const std::string& jsonReq, const PeerIdentity& peer);
    std::string HandleProviderRequest(const std::string& jsonReq, const PeerIdentity& peer);

private:
    struct Challenge {
        std::string id;
        Bytes nonce;
        int64_t expiresAt = 0;
    };

    struct PendingEnrollment {
        std::string token;
        std::wstring userSid;
        std::wstring qualifiedUser;
        std::string vaultMode;
        Bytes vaultIv;
        Bytes vaultDpapi;
        int64_t expiresAt = 0;
    };

    struct PendingCredential {
        std::string attemptId;
        std::wstring userSid;
        std::wstring qualifiedUser;
        std::wstring password;
        int64_t expiresAt = 0;
        bool consumed = false;
        ~PendingCredential() { Wipe(password); }
    };

    struct AttemptResult {
        std::string attemptId;
        bool completed = false;
        bool unlocked = false;
        uint32_t ntstatus = 0xC0000001;
        uint32_t substatus = 0;
        std::string errorCode;
        std::string message;
    };

    bool LoadOrCreateState();
    bool SaveStateLocked();
    bool DpapiProtect(const Bytes& plain, Bytes& out) const;
    bool DpapiUnprotect(const Bytes& blob, Bytes& out) const;
    bool IsRateLimitedLocked(int64_t now, int64_t& retryAfterOut);
    void RecordFailureLocked(int64_t now);
    void ControlLoop();
    void ProviderLoop();

    EngineConfig cfg_;
    std::mutex mu_;
    std::atomic<bool> running_{false};
    HANDLE stopEvent_ = nullptr;
    HANDLE readyEvent_ = nullptr;
    HANDLE resultEvent_ = nullptr;
    std::thread controlThread_;
    std::thread providerThread_;

    // Persistent state
    EcdhKey pcEcdh_;
    bool enrolled_ = false;
    std::string deviceId_;
    std::string deviceName_;
    Bytes phonePub_;
    std::wstring userSid_;
    std::wstring qualifiedUser_;
    std::string vaultMode_;
    Bytes vaultIv_;
    Bytes vaultDpapi_;

    // Ephemeral state
    PendingEnrollment pendingEnroll_;
    std::map<std::string, Challenge> challenges_;
    std::map<std::string, int64_t> usedNonces_;
    std::vector<int64_t> failures_;
    int64_t lockoutUntil_ = 0;

    PendingCredential pendingCred_;
    AttemptResult lastResult_;
    int64_t providerPollCount_ = 0;
    int64_t lastProviderPollAt_ = 0;
};

}  // namespace pcpr
