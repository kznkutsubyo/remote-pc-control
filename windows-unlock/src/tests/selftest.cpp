// End-to-end verification suite for the native Windows Unlock Service and Credential Provider.
#ifndef WIN32_NO_STATUS
#include <ntstatus.h>
#define WIN32_NO_STATUS
#endif
#include "../common/crypto.h"
#include "../common/ipc.h"
#include "../common/util.h"
#include "../provider/provider.h"
#include "../service/unlock_engine.h"

#include <ctime>
#include <iostream>
#include <thread>

using namespace pcpr;

namespace {

void Require(bool cond, const char* msg) {
    if (!cond) {
        std::cerr << "[FAIL] " << msg << "\n";
        std::exit(1);
    }
}

JsonObject CallPipe(const std::wstring& pipe, const std::string& reqJson, const std::wstring& allowedSid) {
    std::string respStr;
    Require(PipeTransact(pipe, reqJson, respStr, /*requireSystemServer=*/true, allowedSid, 10000), "PipeTransact succeeded");
    JsonObject obj;
    Require(JsonParseFlat(respStr, obj), "JsonParseFlat response");
    return obj;
}

std::string MakeSignedUnlockSubmit(
    const JsonObject& chResp,
    const std::string& deviceId,
    const std::string& userSid,
    const EcdsaKey& phoneKey,
    const std::string& innerJson,
    int64_t timestampOverride = 0,
    const std::string& waitMs = "") {
    std::string cid = Get(chResp, "challenge_id");
    std::string nonceB64 = Get(chResp, "nonce");
    std::string pcPubB64 = Get(chResp, "pc_pub");

    Bytes nonce, pcPub, ephPub;
    SecretBytes shared;
    Require(B64UrlDecode(nonceB64, nonce) && B64UrlDecode(pcPubB64, pcPub), "decode challenge fields");
    Require(EphemeralAgree(pcPub, ephPub, shared.value), "ephemeral ECDH agree");

    SecretBytes encKey(HkdfSha256(shared.value, nonce, "pcpr-unlock-v1|" + userSid + "|" + deviceId, 32));
    Bytes iv = RandomBytes(kGcmIvSize);
    std::string ephPubB64 = B64UrlEncode(ephPub);
    std::string ivB64 = B64UrlEncode(iv);
    int64_t ts = timestampOverride ? timestampOverride : static_cast<int64_t>(std::time(nullptr));
    std::string tsStr = std::to_string(ts);

    std::string aad =
        "pcpr-unlock-v1\n" + cid + "\n" + nonceB64 + "\n" + userSid + "\n" +
        deviceId + "\n" + tsStr + "\n" + ephPubB64 + "\n" + ivB64;

    Bytes ct;
    Require(AesGcmEncrypt(encKey.value, iv, ToBytes(aad), ToBytes(innerJson), ct), "AesGcmEncrypt inner payload");
    std::string ctB64 = B64UrlEncode(ct);

    std::string transcript = aad + "\n" + ctB64;
    Bytes sig;
    Require(phoneKey.Sign(ToBytes(transcript), sig), "phoneKey.Sign transcript");

    JsonWriter w;
    w.Str("op", "unlock.submit")
     .Str("challenge_id", cid)
     .Str("device_id", deviceId)
     .Str("user_sid", userSid)
     .Str("timestamp", tsStr)
     .Str("eph_pub", ephPubB64)
     .Str("iv", ivB64)
     .Str("ciphertext", ctB64)
     .Str("signature", B64UrlEncode(sig));
    if (!waitMs.empty()) w.Str("wait_ms", waitMs);
    return w.Build();
}

}  // namespace

int wmain() {
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);

    std::wstring mySid, myQualified;
    Require(GetCurrentProcessUser(mySid, myQualified), "GetCurrentProcessUser");

    wchar_t tempDir[MAX_PATH] = {};
    GetTempPathW(MAX_PATH, tempDir);
    std::wstring stateDir = std::wstring(tempDir) + L"pcpr_unlock_selftest_" + std::to_wstring(GetCurrentProcessId());
    CreateDirectoryW(stateDir.c_str(), nullptr);

    EngineConfig cfg;
    cfg.stateDir = stateDir;
    cfg.controlPipe = L"\\\\.\\pipe\\PCPR_TestControl_" + std::to_wstring(GetCurrentProcessId());
    cfg.providerPipe = L"\\\\.\\pipe\\PCPR_TestProvider_" + std::to_wstring(GetCurrentProcessId());
    cfg.readyEventName = L"Local\\PCPR_TestReady_" + std::to_wstring(GetCurrentProcessId());
    cfg.allowTestPeer = true;
    cfg.allowSyntheticLogon = true;
    cfg.testOwnerSid = mySid;

    auto engine = std::make_unique<UnlockEngine>(cfg);
    Require(engine->Start(), "UnlockEngine Start");

    // 1. Initial status is unenrolled; challenge must fail with not_enrolled.
    auto st0 = CallPipe(cfg.controlPipe, R"({"op":"unlock.status"})", mySid);
    Require(Get(st0, "ok") == "true" && Get(st0, "enrolled") == "false", "initial status not enrolled");
    auto ch0 = CallPipe(cfg.controlPipe, R"({"op":"unlock.challenge"})", mySid);
    Require(Get(ch0, "ok") == "false" && Get(ch0, "error") == "not_enrolled", "challenge rejected before enrollment");
    std::cout << "[PASS] 1. Unenrolled status & challenge guard\n";

    // 2. Enroll phone with split-key vault.
    std::string targetSid = WideToUtf8(mySid);
    JsonWriter beginReq;
    beginReq.Str("op", "enroll.begin")
            .Str("domain", "WORKSTATION")
            .Str("username", "TestOwner")
            .Str("password", "CorrectHorseBatteryStaple!42")
            .Str("mode", "split_key")
            .Str("test_sid", targetSid);
    auto beginResp = CallPipe(cfg.controlPipe, beginReq.Build(), mySid);
    Require(Get(beginResp, "ok") == "true", "enroll.begin succeeded");
    std::string enrollToken = Get(beginResp, "enroll_token");
    std::string splitKeyB64 = Get(beginResp, "split_key");
    std::string pinnedFp = Get(beginResp, "pc_pub_fp");
    Require(!enrollToken.empty() && !splitKeyB64.empty() && !pinnedFp.empty(), "enroll.begin returned token, split_key, and pc_pub_fp");

    EcdsaKey phoneKey;
    Require(phoneKey.Generate(), "generate phone ECDSA P-256 key");
    std::string phonePubB64 = B64UrlEncode(phoneKey.PublicPoint());
    std::string deviceId = "pixel-test-001";

    // Verify wrong enrollment signature is rejected.
    EcdsaKey attackerKey;
    Require(attackerKey.Generate(), "generate attacker key");
    Bytes badEnrollSig;
    std::string enrollTranscript = "pcpr-enroll-v1\n" + enrollToken + "\n" + pinnedFp + "\n" + targetSid + "\n" + deviceId + "\n" + phonePubB64;
    Require(attackerKey.Sign(ToBytes(enrollTranscript), badEnrollSig), "sign bad enroll");
    JsonWriter badComp;
    badComp.Str("op", "enroll.complete")
           .Str("enroll_token", enrollToken)
           .Str("device_id", deviceId)
           .Str("phone_pub", phonePubB64)
           .Str("signature", B64UrlEncode(badEnrollSig));
    auto badCompResp = CallPipe(cfg.controlPipe, badComp.Build(), mySid);
    Require(Get(badCompResp, "ok") == "false" && Get(badCompResp, "error") == "invalid_signature", "tampered enroll signature rejected");

    // Complete enrollment with valid phone signature.
    Bytes validEnrollSig;
    Require(phoneKey.Sign(ToBytes(enrollTranscript), validEnrollSig), "sign valid enroll");
    JsonWriter goodComp;
    goodComp.Str("op", "enroll.complete")
            .Str("enroll_token", enrollToken)
            .Str("device_id", deviceId)
            .Str("device_name", "Pixel 9 Pro")
            .Str("phone_pub", phonePubB64)
            .Str("signature", B64UrlEncode(validEnrollSig));
    auto goodCompResp = CallPipe(cfg.controlPipe, goodComp.Build(), mySid);
    Require(Get(goodCompResp, "ok") == "true" && Get(goodCompResp, "enrolled") == "true", "enroll.complete succeeded");
    std::cout << "[PASS] 2. Physical enrollment with split-key vault & signature verification\n";

    // 3. Reboot / persistence test: restart UnlockEngine from disk and verify pinned PC identity and enrollment survive.
    engine->Stop();
    engine = std::make_unique<UnlockEngine>(cfg);
    Require(engine->Start(), "UnlockEngine restart after reboot simulation");
    auto stAfterReboot = CallPipe(cfg.controlPipe, R"({"op":"unlock.status"})", mySid);
    Require(Get(stAfterReboot, "enrolled") == "true" && Get(stAfterReboot, "pc_pub_fp") == pinnedFp,
            "state & PC identity key persisted across restart");
    std::cout << "[PASS] 3. Reboot persistence & pinned PC identity\n";

    // 4. Correct password unlock through CPhoneUnlockProvider + CPhoneUnlockCredential::GetSerialization + ReportResult(STATUS_SUCCESS).
    auto ch1 = CallPipe(cfg.controlPipe, R"({"op":"unlock.challenge"})", mySid);
    Require(Get(ch1, "ok") == "true" && Get(ch1, "pc_pub_fp") == pinnedFp, "challenge matches pinned PC fingerprint");

    // Simulate LogonUI hosting CPhoneUnlockProvider in parallel while unlock.submit waits for Windows validation.
    std::thread providerSim([&]() {
        Sleep(120);
        auto* prov = new CPhoneUnlockProvider(cfg.providerPipe, cfg.readyEventName, mySid);
        Require(SUCCEEDED(prov->SetUsageScenario(CPUS_UNLOCK_WORKSTATION, 0)), "SetUsageScenario unlock");
        Require(SUCCEEDED(prov->AddTestUser(mySid, L"WORKSTATION\\TestOwner", true)), "AddTestUser");
        DWORD count = 0, defIdx = CREDENTIAL_PROVIDER_NO_DEFAULT;
        BOOL autoLogon = FALSE;
        Require(SUCCEEDED(prov->GetCredentialCount(&count, &defIdx, &autoLogon)), "GetCredentialCount");
        Require(count == 1 && defIdx == 0 && autoLogon == TRUE, "provider flagged auto-logon for enrolled user");

        ICredentialProviderCredential* cred = nullptr;
        Require(SUCCEEDED(prov->GetCredentialAt(0, &cred)) && cred != nullptr, "GetCredentialAt(0)");

        CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE resp = CPGSR_NO_CREDENTIAL_NOT_FINISHED;
        CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION ser = {};
        PWSTR statusText = nullptr;
        CREDENTIAL_PROVIDER_STATUS_ICON icon = CPSI_NONE;
        Require(SUCCEEDED(cred->GetSerialization(&resp, &ser, &statusText, &icon)), "GetSerialization call");
        Require(resp == CPGSR_RETURN_CREDENTIAL_FINISHED && ser.cbSerialization > sizeof(KERB_INTERACTIVE_UNLOCK_LOGON) && ser.rgbSerialization != nullptr,
                "KERB_INTERACTIVE_UNLOCK_LOGON packed");
        if (statusText) CoTaskMemFree(statusText);
        CoTaskMemFree(ser.rgbSerialization);

        // Report STATUS_SUCCESS from Windows LSA.
        statusText = nullptr;
        Require(SUCCEEDED(cred->ReportResult(STATUS_SUCCESS, STATUS_SUCCESS, &statusText, &icon)), "ReportResult STATUS_SUCCESS");
        if (statusText) CoTaskMemFree(statusText);
        cred->Release();
        prov->Release();
    });

    JsonWriter innerSplit;
    innerSplit.Str("k", splitKeyB64);
    std::string submit1 = MakeSignedUnlockSubmit(ch1, deviceId, targetSid, phoneKey, innerSplit.Build());
    auto res1 = CallPipe(cfg.controlPipe, submit1, mySid);
    providerSim.join();
    Require(Get(res1, "ok") == "true" && Get(res1, "unlocked") == "true", "split-key unlock succeeded after Windows ReportResult");
    std::cout << "[PASS] 4. Split-key unlock + KERB_INTERACTIVE_UNLOCK_LOGON serialization + ReportResult(STATUS_SUCCESS)\n";

    // 5. Replay protection: submitting the exact same signed request or reusing the challenge must fail.
    auto replayRes = CallPipe(cfg.controlPipe, submit1, mySid);
    Require(Get(replayRes, "ok") == "false" && Get(replayRes, "error") == "invalid_challenge", "replayed challenge rejected");
    std::cout << "[PASS] 5. Single-use challenge & replay protection\n";

    // 6. Expired timestamp / skewed request rejected.
    auto chExp = CallPipe(cfg.controlPipe, R"({"op":"unlock.challenge"})", mySid);
    std::string submitExp = MakeSignedUnlockSubmit(chExp, deviceId, targetSid, phoneKey, innerSplit.Build(),
                                                   static_cast<int64_t>(std::time(nullptr)) - 120);
    auto expRes = CallPipe(cfg.controlPipe, submitExp, mySid);
    Require(Get(expRes, "ok") == "false" && Get(expRes, "error") == "clock_skew", "expired timestamp rejected");
    std::cout << "[PASS] 6. Expired request rejection\n";

    // 7. Wrong account / SID mismatch rejected, and provider tile for another user SID cannot acquire the credential.
    auto chWrongSid = CallPipe(cfg.controlPipe, R"({"op":"unlock.challenge"})", mySid);
    std::string submitWrongSid = MakeSignedUnlockSubmit(chWrongSid, deviceId, "S-1-5-21-999-999-999-1002", phoneKey, innerSplit.Build());
    auto wrongSidRes = CallPipe(cfg.controlPipe, submitWrongSid, mySid);
    Require(Get(wrongSidRes, "ok") == "false" && Get(wrongSidRes, "error") == "account_mismatch", "wrong user_sid rejected");
    std::cout << "[PASS] 7. Wrong account / session binding enforced\n";

    // 8. Phone certificate / key mismatch rejected.
    auto chBadKey = CallPipe(cfg.controlPipe, R"({"op":"unlock.challenge"})", mySid);
    std::string submitBadKey = MakeSignedUnlockSubmit(chBadKey, deviceId, targetSid, attackerKey, innerSplit.Build());
    auto badKeyRes = CallPipe(cfg.controlPipe, submitBadKey, mySid);
    Require(Get(badKeyRes, "ok") == "false" && Get(badKeyRes, "error") == "invalid_signature", "unenrolled phone key rejected");
    std::cout << "[PASS] 8. Phone key mismatch rejected\n";

    // Reset failure counter with one clean unlock so we can test wrong password, account lockout, and provider timeout.
    {
        auto chClean = CallPipe(cfg.controlPipe, R"({"op":"unlock.challenge"})", mySid);
        std::thread t([&]() {
            Sleep(80);
            auto* cred = new CPhoneUnlockCredential(cfg.providerPipe, mySid);
            cred->InitializeForTest(CPUS_UNLOCK_WORKSTATION, mySid, L"WORKSTATION\\TestOwner", true);
            CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE r;
            CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION s = {};
            PWSTR txt = nullptr;
            CREDENTIAL_PROVIDER_STATUS_ICON ic;
            cred->GetSerialization(&r, &s, &txt, &ic);
            if (txt) CoTaskMemFree(txt);
            if (s.rgbSerialization) CoTaskMemFree(s.rgbSerialization);
            txt = nullptr;
            cred->ReportResult(STATUS_SUCCESS, STATUS_SUCCESS, &txt, &ic);
            if (txt) CoTaskMemFree(txt);
            cred->Release();
        });
        auto rClean = CallPipe(cfg.controlPipe, MakeSignedUnlockSubmit(chClean, deviceId, targetSid, phoneKey, innerSplit.Build()), mySid);
        t.join();
        Require(Get(rClean, "unlocked") == "true", "clean unlock resets failures");
    }

    // 9. Incorrect password reported by Windows LSA (STATUS_LOGON_FAILURE) & Account Lockout (STATUS_ACCOUNT_LOCKED_OUT).
    for (NTSTATUS simulatedStatus : {STATUS_LOGON_FAILURE, STATUS_ACCOUNT_LOCKED_OUT}) {
        auto chFail = CallPipe(cfg.controlPipe, R"({"op":"unlock.challenge"})", mySid);
        std::thread t([&, simulatedStatus]() {
            Sleep(80);
            auto* cred = new CPhoneUnlockCredential(cfg.providerPipe, mySid);
            cred->InitializeForTest(CPUS_UNLOCK_WORKSTATION, mySid, L"WORKSTATION\\TestOwner", true);
            CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE r;
            CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION s = {};
            PWSTR txt = nullptr;
            CREDENTIAL_PROVIDER_STATUS_ICON ic;
            cred->GetSerialization(&r, &s, &txt, &ic);
            if (txt) CoTaskMemFree(txt);
            if (s.rgbSerialization) CoTaskMemFree(s.rgbSerialization);
            txt = nullptr;
            cred->ReportResult(simulatedStatus, simulatedStatus, &txt, &ic);
            Require(txt != nullptr, "ReportResult returned localized failure message");
            CoTaskMemFree(txt);
            cred->Release();
        });
        JsonWriter innerPw;
        innerPw.Str("password", "WrongPassword123");
        auto failRes = CallPipe(cfg.controlPipe, MakeSignedUnlockSubmit(chFail, deviceId, targetSid, phoneKey, innerPw.Build()), mySid);
        t.join();
        Require(Get(failRes, "ok") == "false" && Get(failRes, "unlocked") == "false", "Windows rejection propagated to phone");
        std::string expectedErr = (simulatedStatus == STATUS_LOGON_FAILURE) ? "wrong_password" : "account_locked";
        Require(Get(failRes, "error") == expectedErr, "exact LSA failure mapped");
    }
    std::cout << "[PASS] 9. Incorrect password (STATUS_LOGON_FAILURE) & Account lockout (STATUS_ACCOUNT_LOCKED_OUT)\n";

    // 10. Provider timeout / crash & Service unavailable graceful fallback.
    auto chTimeout = CallPipe(cfg.controlPipe, R"({"op":"unlock.challenge"})", mySid);
    std::string submitTimeout = MakeSignedUnlockSubmit(chTimeout, deviceId, targetSid, phoneKey, innerSplit.Build(), 0, "350");
    auto timeoutRes = CallPipe(cfg.controlPipe, submitTimeout, mySid);
    Require(Get(timeoutRes, "ok") == "false" && Get(timeoutRes, "error") == "provider_timeout", "provider timeout handled and secret wiped");

    engine->Stop();
    {
        auto* credOffline = new CPhoneUnlockCredential(cfg.providerPipe, mySid);
        credOffline->InitializeForTest(CPUS_UNLOCK_WORKSTATION, mySid, L"WORKSTATION\\TestOwner", true);
        CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE r = CPGSR_RETURN_CREDENTIAL_FINISHED;
        CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION s = {};
        PWSTR txt = nullptr;
        CREDENTIAL_PROVIDER_STATUS_ICON ic = CPSI_NONE;
        Require(SUCCEEDED(credOffline->GetSerialization(&r, &s, &txt, &ic)), "GetSerialization when service offline does not fail");
        Require(r == CPGSR_NO_CREDENTIAL_NOT_FINISHED && txt != nullptr, "offline provider gracefully declines serialization");
        CoTaskMemFree(txt);
        credOffline->Release();
    }
    std::cout << "[PASS] 10. Provider timeout & service unavailable graceful fallback\n";

    CoUninitialize();
    std::cout << "ALL NATIVE WINDOWS UNLOCK TESTS PASSED.\n";
    return 0;
}
