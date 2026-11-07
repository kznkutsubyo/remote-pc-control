#include "provider.h"
#include <intsafe.h>

#pragma comment(lib, "credui.lib")
#pragma comment(lib, "secur32.lib")
#pragma comment(lib, "shlwapi.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "uuid.lib")
#pragma comment(lib, "propsys.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "advapi32.lib")

namespace pcpr {

// {D7F4C9E2-54C9-4E6D-9B0C-48E71F6A8C21}
const CLSID CLSID_PhoneUnlockProvider = {
    0xd7f4c9e2, 0x54c9, 0x4e6d, {0x9b, 0x0c, 0x48, 0xe7, 0x1f, 0x6a, 0x8c, 0x21}
};

// Identity_LocalUserProvider: {A198529B-730F-4089-B646-A12557F5665E}
const GUID kIdentityLocalUserProvider = {
    0xa198529b, 0x730f, 0x4089, {0xb6, 0x46, 0xa1, 0x25, 0x57, 0xf5, 0x66, 0x5e}
};

namespace {

LONG g_dllRefCount = 0;
HINSTANCE g_hInstance = nullptr;

const CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR kFieldDescriptors[PFI_NUM_FIELDS] = {
    {PFI_TILEIMAGE, CPFT_TILE_IMAGE, const_cast<LPWSTR>(L"Image"), CPFG_CREDENTIAL_PROVIDER_LOGO},
    {PFI_LABEL, CPFT_SMALL_TEXT, const_cast<LPWSTR>(L"PC Phone Remote"), CPFG_CREDENTIAL_PROVIDER_LABEL},
    {PFI_LARGE_TEXT, CPFT_LARGE_TEXT, const_cast<LPWSTR>(L"Phone Sign-In")},
    {PFI_SMALL_TEXT, CPFT_SMALL_TEXT, const_cast<LPWSTR>(L"Status")},
    {PFI_SUBMIT_BUTTON, CPFT_SUBMIT_BUTTON, const_cast<LPWSTR>(L"Sign in")},
};

HRESULT UnicodeStringInitWithString(PWSTR pwz, UNICODE_STRING* pus) {
    if (!pwz || !pus) return E_INVALIDARG;
    size_t len = wcslen(pwz);
    USHORT chars = 0;
    HRESULT hr = SizeTToUShort(len, &chars);
    if (FAILED(hr)) return hr;
    hr = UShortMult(chars, sizeof(wchar_t), &pus->Length);
    if (FAILED(hr)) return hr;
    pus->MaximumLength = pus->Length;
    pus->Buffer = pwz;
    return S_OK;
}

void PackedUnicodeStringCopy(const UNICODE_STRING& rus, PWSTR pwzBuffer, UNICODE_STRING* pus) {
    pus->Length = rus.Length;
    pus->MaximumLength = rus.Length;
    pus->Buffer = pwzBuffer;
    CopyMemory(pus->Buffer, rus.Buffer, pus->Length);
}

HRESULT KerbInteractiveUnlockLogonInit(
    PWSTR pwzDomain,
    PWSTR pwzUsername,
    PWSTR pwzPassword,
    CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus,
    KERB_INTERACTIVE_UNLOCK_LOGON* pkiul) {
    ZeroMemory(pkiul, sizeof(*pkiul));
    KERB_INTERACTIVE_LOGON* pkil = &pkiul->Logon;
    HRESULT hr = UnicodeStringInitWithString(pwzDomain, &pkil->LogonDomainName);
    if (FAILED(hr)) return hr;
    hr = UnicodeStringInitWithString(pwzUsername, &pkil->UserName);
    if (FAILED(hr)) return hr;
    hr = UnicodeStringInitWithString(pwzPassword, &pkil->Password);
    if (FAILED(hr)) return hr;

    switch (cpus) {
    case CPUS_UNLOCK_WORKSTATION:
        pkil->MessageType = KerbWorkstationUnlockLogon;
        return S_OK;
    case CPUS_LOGON:
        pkil->MessageType = KerbInteractiveLogon;
        return S_OK;
    default:
        return E_FAIL;
    }
}

HRESULT KerbInteractiveUnlockLogonPack(
    const KERB_INTERACTIVE_UNLOCK_LOGON& rkiulIn,
    BYTE** prgb,
    DWORD* pcb) {
    const KERB_INTERACTIVE_LOGON* pkilIn = &rkiulIn.Logon;
    DWORD cb = sizeof(rkiulIn) +
               pkilIn->LogonDomainName.Length +
               pkilIn->UserName.Length +
               pkilIn->Password.Length;
    auto* pkiulOut = static_cast<KERB_INTERACTIVE_UNLOCK_LOGON*>(CoTaskMemAlloc(cb));
    if (!pkiulOut) return E_OUTOFMEMORY;

    ZeroMemory(&pkiulOut->LogonId, sizeof(pkiulOut->LogonId));
    BYTE* pbBuffer = reinterpret_cast<BYTE*>(pkiulOut) + sizeof(*pkiulOut);
    KERB_INTERACTIVE_LOGON* pkilOut = &pkiulOut->Logon;
    pkilOut->MessageType = pkilIn->MessageType;

    PackedUnicodeStringCopy(pkilIn->LogonDomainName, reinterpret_cast<PWSTR>(pbBuffer), &pkilOut->LogonDomainName);
    pkilOut->LogonDomainName.Buffer = reinterpret_cast<PWSTR>(pbBuffer - reinterpret_cast<BYTE*>(pkiulOut));
    pbBuffer += pkilOut->LogonDomainName.Length;

    PackedUnicodeStringCopy(pkilIn->UserName, reinterpret_cast<PWSTR>(pbBuffer), &pkilOut->UserName);
    pkilOut->UserName.Buffer = reinterpret_cast<PWSTR>(pbBuffer - reinterpret_cast<BYTE*>(pkiulOut));
    pbBuffer += pkilOut->UserName.Length;

    PackedUnicodeStringCopy(pkilIn->Password, reinterpret_cast<PWSTR>(pbBuffer), &pkilOut->Password);
    pkilOut->Password.Buffer = reinterpret_cast<PWSTR>(pbBuffer - reinterpret_cast<BYTE*>(pkiulOut));

    *prgb = reinterpret_cast<BYTE*>(pkiulOut);
    *pcb = cb;
    return S_OK;
}

HRESULT RetrieveNegotiateAuthPackage(ULONG* pulAuthPackage) {
    HANDLE hLsa = nullptr;
    NTSTATUS status = LsaConnectUntrusted(&hLsa);
    if (FAILED(HRESULT_FROM_NT(status))) return HRESULT_FROM_NT(status);

    LSA_STRING name = {};
    name.Buffer = const_cast<PCHAR>(NEGOSSP_NAME_A);
    name.Length = static_cast<USHORT>(strlen(NEGOSSP_NAME_A));
    name.MaximumLength = name.Length + 1;

    ULONG pkg = 0;
    status = LsaLookupAuthenticationPackage(hLsa, &name, &pkg);
    LsaDeregisterLogonProcess(hLsa);
    if (FAILED(HRESULT_FROM_NT(status))) return HRESULT_FROM_NT(status);
    *pulAuthPackage = pkg;
    return S_OK;
}

HRESULT ProtectPasswordCopy(PCWSTR pwzPassword, CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus, PWSTR* ppwzProtected) {
    *ppwzProtected = nullptr;
    if (!pwzPassword || !*pwzPassword) return SHStrDupW(L"", ppwzProtected);

    PWSTR copy = nullptr;
    HRESULT hr = SHStrDupW(pwzPassword, &copy);
    if (FAILED(hr)) return hr;
    size_t cchCopy = wcslen(copy);

    CRED_PROTECTION_TYPE protType = CredUnprotected;
    bool alreadyEncrypted = CredIsProtectedW(copy, &protType) && (protType != CredUnprotected);
    if (cpus == CPUS_CREDUI || alreadyEncrypted) {
        hr = SHStrDupW(copy, ppwzProtected);
    } else {
        DWORD cchProtected = 0;
        hr = E_FAIL;
        if (!CredProtectW(FALSE, copy, static_cast<DWORD>(cchCopy + 1), nullptr, &cchProtected, nullptr) &&
            GetLastError() == ERROR_INSUFFICIENT_BUFFER && cchProtected > 0) {
            PWSTR buf = static_cast<PWSTR>(CoTaskMemAlloc(cchProtected * sizeof(wchar_t)));
            if (buf) {
                if (CredProtectW(FALSE, copy, static_cast<DWORD>(cchCopy + 1), buf, &cchProtected, nullptr)) {
                    *ppwzProtected = buf;
                    hr = S_OK;
                } else {
                    hr = HRESULT_FROM_WIN32(GetLastError());
                    CoTaskMemFree(buf);
                }
            } else {
                hr = E_OUTOFMEMORY;
            }
        }
    }
    SecureZeroMemory(copy, cchCopy * sizeof(wchar_t));
    CoTaskMemFree(copy);
    return hr;
}

HRESULT SplitDomainAndUser(PCWSTR qualified, PWSTR* ppDomain, PWSTR* ppUser) {
    *ppDomain = nullptr;
    *ppUser = nullptr;
    if (!qualified) return E_INVALIDARG;
    const wchar_t* slash = wcschr(qualified, L'\\');
    if (!slash) {
        HRESULT hr = SHStrDupW(L".", ppDomain);
        if (SUCCEEDED(hr)) hr = SHStrDupW(qualified, ppUser);
        return hr;
    }
    size_t domLen = static_cast<size_t>(slash - qualified);
    *ppDomain = static_cast<PWSTR>(CoTaskMemAlloc((domLen + 1) * sizeof(wchar_t)));
    if (!*ppDomain) return E_OUTOFMEMORY;
    StringCchCopyNW(*ppDomain, domLen + 1, qualified, domLen);
    HRESULT hr = SHStrDupW(slash + 1, ppUser);
    if (FAILED(hr)) {
        CoTaskMemFree(*ppDomain);
        *ppDomain = nullptr;
    }
    return hr;
}

}  // namespace

void DllAddRef() { InterlockedIncrement(&g_dllRefCount); }
void DllRelease() { InterlockedDecrement(&g_dllRefCount); }

// ================================================================ CPhoneUnlockCredential

CPhoneUnlockCredential::CPhoneUnlockCredential(
    const std::wstring& providerPipe,
    const std::wstring& allowedServerSid)
    : providerPipe_(providerPipe), allowedServerSid_(allowedServerSid) {
    DllAddRef();
}

CPhoneUnlockCredential::~CPhoneUnlockCredential() {
    if (events_) {
        events_->Release();
        events_ = nullptr;
    }
    DllRelease();
}

ULONG CPhoneUnlockCredential::AddRef() { return InterlockedIncrement(&refCount_); }

ULONG CPhoneUnlockCredential::Release() {
    LONG c = InterlockedDecrement(&refCount_);
    if (!c) delete this;
    return c;
}

HRESULT CPhoneUnlockCredential::QueryInterface(REFIID riid, void** ppv) {
    if (!ppv) return E_INVALIDARG;
    *ppv = nullptr;
    if (riid == IID_IUnknown || riid == IID_ICredentialProviderCredential || riid == IID_ICredentialProviderCredential2) {
        *ppv = static_cast<ICredentialProviderCredential2*>(this);
    } else if (riid == IID_ICredentialProviderCredentialWithFieldOptions) {
        *ppv = static_cast<ICredentialProviderCredentialWithFieldOptions*>(this);
    } else {
        return E_NOINTERFACE;
    }
    AddRef();
    return S_OK;
}

HRESULT CPhoneUnlockCredential::Initialize(
    CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus,
    ICredentialProviderUser* pcpUser) {
    if (!pcpUser) return E_INVALIDARG;
    cpus_ = cpus;

    GUID providerId = {};
    if (SUCCEEDED(pcpUser->GetProviderID(&providerId))) {
        isLocalUser_ = IsEqualGUID(providerId, kIdentityLocalUserProvider) != FALSE;
    }

    PWSTR sid = nullptr;
    HRESULT hr = pcpUser->GetSid(&sid);
    if (FAILED(hr) || !sid) return E_FAIL;
    userSid_ = sid;
    CoTaskMemFree(sid);

    PWSTR qName = nullptr;
    if (SUCCEEDED(pcpUser->GetStringValue(PKEY_Identity_QualifiedUserName, &qName)) && qName) {
        qualifiedUser_ = qName;
        CoTaskMemFree(qName);
    }
    return S_OK;
}

HRESULT CPhoneUnlockCredential::InitializeForTest(
    CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus,
    const std::wstring& userSid,
    const std::wstring& qualifiedUserName,
    bool isLocalUser) {
    cpus_ = cpus;
    userSid_ = userSid;
    qualifiedUser_ = qualifiedUserName;
    isLocalUser_ = isLocalUser;
    return S_OK;
}

void CPhoneUnlockCredential::SetPendingAttempt(const std::string& attemptId) {
    lastAttemptId_ = attemptId;
    pendingAutoLogon_.store(true);
}

bool CPhoneUnlockCredential::ConsumeAutoLogonFlag() {
    // Keep pendingAutoLogon_ set until GetSerialization (or SetDeselected) so that
    // both GetCredentialCount (*pbAutoLogonWithDefault) and SetSelected (*pbAutoLogon)
    // report TRUE to LogonUI.exe.
    return pendingAutoLogon_.load();
}

HRESULT CPhoneUnlockCredential::Advise(ICredentialProviderCredentialEvents* pcpce) {
    if (events_) events_->Release();
    events_ = pcpce;
    if (events_) events_->AddRef();
    return S_OK;
}

HRESULT CPhoneUnlockCredential::UnAdvise() {
    if (events_) {
        events_->Release();
        events_ = nullptr;
    }
    return S_OK;
}

HRESULT CPhoneUnlockCredential::SetSelected(BOOL* pbAutoLogon) {
    if (!pbAutoLogon) return E_INVALIDARG;
    *pbAutoLogon = pendingAutoLogon_.load() ? TRUE : FALSE;
    return S_OK;
}

HRESULT CPhoneUnlockCredential::SetDeselected() { return S_OK; }

HRESULT CPhoneUnlockCredential::GetFieldState(
    DWORD dwFieldID,
    CREDENTIAL_PROVIDER_FIELD_STATE* pcpfs,
    CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE* pcpfis) {
    if (!pcpfs || !pcpfis || dwFieldID >= PFI_NUM_FIELDS) return E_INVALIDARG;
    *pcpfis = CPFIS_NONE;
    switch (dwFieldID) {
    case PFI_TILEIMAGE:
    case PFI_LARGE_TEXT:
    case PFI_SMALL_TEXT:
    case PFI_SUBMIT_BUTTON:
        *pcpfs = CPFS_DISPLAY_IN_SELECTED_TILE;
        break;
    case PFI_LABEL:
        *pcpfs = CPFS_DISPLAY_IN_DESELECTED_TILE;
        break;
    default:
        *pcpfs = CPFS_HIDDEN;
        break;
    }
    return S_OK;
}

HRESULT CPhoneUnlockCredential::GetStringValue(DWORD dwFieldID, PWSTR* ppwsz) {
    if (!ppwsz) return E_INVALIDARG;
    *ppwsz = nullptr;
    switch (dwFieldID) {
    case PFI_LABEL:
        return SHStrDupW(L"Вход с телефона (PC Remote)", ppwsz);
    case PFI_LARGE_TEXT:
        return SHStrDupW(L"Вход с телефона", ppwsz);
    case PFI_SMALL_TEXT:
        return SHStrDupW(L"Откройте приложение PC Remote на телефоне и подтвердите вход", ppwsz);
    case PFI_SUBMIT_BUTTON:
        return SHStrDupW(L"Проверить запрос с телефона", ppwsz);
    default:
        return E_INVALIDARG;
    }
}

HRESULT CPhoneUnlockCredential::GetBitmapValue(DWORD, HBITMAP* phbmp) {
    if (!phbmp) return E_INVALIDARG;
    *phbmp = nullptr;
    return E_NOTIMPL;
}

HRESULT CPhoneUnlockCredential::GetCheckboxValue(DWORD, BOOL*, PWSTR*) { return E_NOTIMPL; }

HRESULT CPhoneUnlockCredential::GetSubmitButtonValue(DWORD dwFieldID, DWORD* pdwAdjacentTo) {
    if (!pdwAdjacentTo || dwFieldID != PFI_SUBMIT_BUTTON) return E_INVALIDARG;
    *pdwAdjacentTo = PFI_SMALL_TEXT;
    return S_OK;
}

HRESULT CPhoneUnlockCredential::GetComboBoxValueCount(DWORD, DWORD*, DWORD*) { return E_NOTIMPL; }
HRESULT CPhoneUnlockCredential::GetComboBoxValueAt(DWORD, DWORD, PWSTR*) { return E_NOTIMPL; }
HRESULT CPhoneUnlockCredential::SetStringValue(DWORD, PCWSTR) { return E_NOTIMPL; }
HRESULT CPhoneUnlockCredential::SetCheckboxValue(DWORD, BOOL) { return E_NOTIMPL; }
HRESULT CPhoneUnlockCredential::SetComboBoxSelectedValue(DWORD, DWORD) { return E_NOTIMPL; }
HRESULT CPhoneUnlockCredential::CommandLinkClicked(DWORD) { return E_NOTIMPL; }

HRESULT CPhoneUnlockCredential::GetSerialization(
    CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE* pcpgsr,
    CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs,
    PWSTR* ppwszOptionalStatusText,
    CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon) {
    if (!pcpgsr || !pcpcs || !ppwszOptionalStatusText || !pcpsiOptionalStatusIcon) return E_INVALIDARG;
    *pcpgsr = CPGSR_NO_CREDENTIAL_NOT_FINISHED;
    *ppwszOptionalStatusText = nullptr;
    *pcpsiOptionalStatusIcon = CPSI_NONE;
    ZeroMemory(pcpcs, sizeof(*pcpcs));
    pendingAutoLogon_.store(false);

    JsonWriter reqW;
    reqW.Str("op", "provider.acquire").Str("user_sid", WideToUtf8(userSid_));
    std::string respStr;
    if (!PipeTransact(providerPipe_, reqW.Build(), respStr, /*requireSystemServer=*/true, allowedServerSid_, 4000)) {
        SHStrDupW(L"Служба PC Remote недоступна. Войдите обычным паролем или PIN.", ppwszOptionalStatusText);
        *pcpsiOptionalStatusIcon = CPSI_WARNING;
        return S_OK;
    }

    JsonObject resp;
    bool parsed = JsonParseFlat(respStr, resp);
    Wipe(respStr);
    if (!parsed || Get(resp, "ok") != "true") {
        for (auto& kv : resp) Wipe(kv.second);
        SHStrDupW(L"Ожидание подтверждения входа на телефоне…", ppwszOptionalStatusText);
        *pcpsiOptionalStatusIcon = CPSI_NONE;
        return S_OK;
    }

    lastAttemptId_ = Get(resp, "attempt_id");
    std::wstring respSid = Utf8ToWide(Get(resp, "user_sid"));
    std::wstring respQualified = Utf8ToWide(Get(resp, "qualified_user"));
    std::wstring password = Utf8ToWide(Get(resp, "password"));
    for (auto& kv : resp) Wipe(kv.second);

    if (_wcsicmp(respSid.c_str(), userSid_.c_str()) != 0 || password.empty()) {
        Wipe(password);
        SHStrDupW(L"Запрос входа предназначен для другой учётной записи.", ppwszOptionalStatusText);
        *pcpsiOptionalStatusIcon = CPSI_ERROR;
        return S_OK;
    }

    const std::wstring& targetQualified = qualifiedUser_.empty() ? respQualified : qualifiedUser_;
    HRESULT hr = E_FAIL;

    if (!isLocalUser_) {
        DWORD flags = CRED_PACK_PROTECTED_CREDENTIALS | CRED_PACK_ID_PROVIDER_CREDENTIALS;
        if (!CredPackAuthenticationBufferW(flags, const_cast<PWSTR>(targetQualified.c_str()),
                                           const_cast<PWSTR>(password.c_str()), nullptr, &pcpcs->cbSerialization) &&
            GetLastError() == ERROR_INSUFFICIENT_BUFFER) {
            pcpcs->rgbSerialization = static_cast<BYTE*>(CoTaskMemAlloc(pcpcs->cbSerialization));
            if (pcpcs->rgbSerialization) {
                if (CredPackAuthenticationBufferW(flags, const_cast<PWSTR>(targetQualified.c_str()),
                                                  const_cast<PWSTR>(password.c_str()),
                                                  pcpcs->rgbSerialization, &pcpcs->cbSerialization)) {
                    ULONG authPkg = 0;
                    hr = RetrieveNegotiateAuthPackage(&authPkg);
                    if (SUCCEEDED(hr)) {
                        pcpcs->ulAuthenticationPackage = authPkg;
                        pcpcs->clsidCredentialProvider = CLSID_PhoneUnlockProvider;
                        *pcpgsr = CPGSR_RETURN_CREDENTIAL_FINISHED;
                    }
                }
                if (*pcpgsr != CPGSR_RETURN_CREDENTIAL_FINISHED) {
                    CoTaskMemFree(pcpcs->rgbSerialization);
                    pcpcs->rgbSerialization = nullptr;
                    pcpcs->cbSerialization = 0;
                }
            }
        }
    }

    if (*pcpgsr != CPGSR_RETURN_CREDENTIAL_FINISHED) {
        PWSTR pwzProtected = nullptr;
        hr = ProtectPasswordCopy(password.c_str(), cpus_, &pwzProtected);
        if (SUCCEEDED(hr)) {
            PWSTR pszDomain = nullptr;
            PWSTR pszUsername = nullptr;
            hr = SplitDomainAndUser(targetQualified.c_str(), &pszDomain, &pszUsername);
            if (SUCCEEDED(hr)) {
                KERB_INTERACTIVE_UNLOCK_LOGON kiul = {};
                hr = KerbInteractiveUnlockLogonInit(pszDomain, pszUsername, pwzProtected, cpus_, &kiul);
                if (SUCCEEDED(hr)) {
                    hr = KerbInteractiveUnlockLogonPack(kiul, &pcpcs->rgbSerialization, &pcpcs->cbSerialization);
                    if (SUCCEEDED(hr)) {
                        ULONG authPkg = 0;
                        hr = RetrieveNegotiateAuthPackage(&authPkg);
                        if (SUCCEEDED(hr)) {
                            pcpcs->ulAuthenticationPackage = authPkg;
                            pcpcs->clsidCredentialProvider = CLSID_PhoneUnlockProvider;
                            *pcpgsr = CPGSR_RETURN_CREDENTIAL_FINISHED;
                        }
                    }
                }
                CoTaskMemFree(pszDomain);
                CoTaskMemFree(pszUsername);
            }
            if (pwzProtected) {
                SecureZeroMemory(pwzProtected, wcslen(pwzProtected) * sizeof(wchar_t));
                CoTaskMemFree(pwzProtected);
            }
        }
    }

    Wipe(password);
    return hr;
}

HRESULT CPhoneUnlockCredential::ReportResult(
    NTSTATUS ntsStatus,
    NTSTATUS ntsSubstatus,
    PWSTR* ppwszOptionalStatusText,
    CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon) {
    if (!ppwszOptionalStatusText || !pcpsiOptionalStatusIcon) return E_INVALIDARG;
    *ppwszOptionalStatusText = nullptr;
    *pcpsiOptionalStatusIcon = CPSI_NONE;

    if (!lastAttemptId_.empty()) {
        JsonWriter w;
        w.Str("op", "provider.report")
         .Str("attempt_id", lastAttemptId_)
         .Int("ntstatus", static_cast<long long>(static_cast<uint32_t>(ntsStatus)))
         .Int("substatus", static_cast<long long>(static_cast<uint32_t>(ntsSubstatus)));
        std::string resp;
        PipeTransact(providerPipe_, w.Build(), resp, /*requireSystemServer=*/true, allowedServerSid_, 3000);
        lastAttemptId_.clear();
    }

    if (ntsStatus == STATUS_LOGON_FAILURE) {
        SHStrDupW(L"Windows отклонила пароль. Проверьте пароль или обновите привязку телефона.", ppwszOptionalStatusText);
        *pcpsiOptionalStatusIcon = CPSI_ERROR;
    } else if (ntsStatus == STATUS_ACCOUNT_LOCKED_OUT || ntsSubstatus == STATUS_ACCOUNT_LOCKED_OUT) {
        SHStrDupW(L"Учётная запись временно заблокирована из-за неверных попыток входа.", ppwszOptionalStatusText);
        *pcpsiOptionalStatusIcon = CPSI_WARNING;
    }
    return S_OK;
}

HRESULT CPhoneUnlockCredential::GetUserSid(PWSTR* ppszSid) {
    if (!ppszSid) return E_INVALIDARG;
    *ppszSid = nullptr;
    if (userSid_.empty()) return E_UNEXPECTED;
    return SHStrDupW(userSid_.c_str(), ppszSid);
}

HRESULT CPhoneUnlockCredential::GetFieldOptions(
    DWORD,
    CREDENTIAL_PROVIDER_CREDENTIAL_FIELD_OPTIONS* pcpcfo) {
    if (!pcpcfo) return E_INVALIDARG;
    *pcpcfo = CPCFO_NONE;
    return S_OK;
}

// ================================================================ CPhoneUnlockProvider

CPhoneUnlockProvider::CPhoneUnlockProvider(
    const std::wstring& providerPipe,
    const std::wstring& readyEventName,
    const std::wstring& allowedServerSid)
    : providerPipe_(providerPipe),
      readyEventName_(readyEventName),
      allowedServerSid_(allowedServerSid) {
    DllAddRef();
    stopWatchEvent_ = CreateEventW(nullptr, TRUE, FALSE, nullptr);
}

CPhoneUnlockProvider::~CPhoneUnlockProvider() {
    UnAdvise();
    ReleaseCredentials();
    if (userArray_) {
        userArray_->Release();
        userArray_ = nullptr;
    }
    if (stopWatchEvent_) CloseHandle(stopWatchEvent_);
    DllRelease();
}

ULONG CPhoneUnlockProvider::AddRef() { return InterlockedIncrement(&refCount_); }

ULONG CPhoneUnlockProvider::Release() {
    LONG c = InterlockedDecrement(&refCount_);
    if (!c) delete this;
    return c;
}

HRESULT CPhoneUnlockProvider::QueryInterface(REFIID riid, void** ppv) {
    if (!ppv) return E_INVALIDARG;
    *ppv = nullptr;
    if (riid == IID_IUnknown || riid == IID_ICredentialProvider) {
        *ppv = static_cast<ICredentialProvider*>(this);
    } else if (riid == IID_ICredentialProviderSetUserArray) {
        *ppv = static_cast<ICredentialProviderSetUserArray*>(this);
    } else {
        return E_NOINTERFACE;
    }
    AddRef();
    return S_OK;
}

HRESULT CPhoneUnlockProvider::SetUsageScenario(CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus, DWORD) {
    switch (cpus) {
    case CPUS_LOGON:
    case CPUS_UNLOCK_WORKSTATION:
        cpus_ = cpus;
        recreateCredentials_ = true;
        return S_OK;
    case CPUS_CHANGE_PASSWORD:
    case CPUS_CREDUI:
        return E_NOTIMPL;
    default:
        return E_INVALIDARG;
    }
}

HRESULT CPhoneUnlockProvider::SetSerialization(const CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION*) {
    return E_NOTIMPL;
}

HRESULT CPhoneUnlockProvider::Advise(ICredentialProviderEvents* pcpe, UINT_PTR upAdviseContext) {
    UnAdvise();
    providerEvents_ = pcpe;
    adviseContext_ = upAdviseContext;
    if (providerEvents_) {
        providerEvents_->AddRef();
        ResetEvent(stopWatchEvent_);
        watching_.store(true);
        watcherThread_ = std::thread([this]() { WatcherLoop(); });
    }
    return S_OK;
}

HRESULT CPhoneUnlockProvider::UnAdvise() {
    if (watching_.exchange(false)) {
        SetEvent(stopWatchEvent_);
        if (watcherThread_.joinable()) watcherThread_.join();
    }
    if (providerEvents_) {
        providerEvents_->Release();
        providerEvents_ = nullptr;
    }
    adviseContext_ = 0;
    return S_OK;
}

void CPhoneUnlockProvider::WatcherLoop() {
    HANDLE readyEv = OpenEventW(SYNCHRONIZE, FALSE, readyEventName_.c_str());
    std::string lastNotifiedAttempt;

    while (watching_.load()) {
        if (readyEv) {
            HANDLE waits[2] = {stopWatchEvent_, readyEv};
            DWORD w = WaitForMultipleObjects(2, waits, FALSE, 250);
            if (w == WAIT_OBJECT_0) break;
        } else {
            if (WaitForSingleObject(stopWatchEvent_, 250) == WAIT_OBJECT_0) break;
            readyEv = OpenEventW(SYNCHRONIZE, FALSE, readyEventName_.c_str());
        }
        if (!watching_.load()) break;

        JsonWriter reqW;
        reqW.Str("op", "provider.poll");
        std::string respStr;
        if (!PipeTransact(providerPipe_, reqW.Build(), respStr, /*requireSystemServer=*/true, allowedServerSid_, 1000)) {
            continue;
        }
        JsonObject resp;
        if (JsonParseFlat(respStr, resp) && Get(resp, "ok") == "true" && Get(resp, "has_pending") == "true") {
            std::string attemptId = Get(resp, "attempt_id");
            std::wstring targetSid = Utf8ToWide(Get(resp, "user_sid"));
            if (!attemptId.empty() && attemptId != lastNotifiedAttempt) {
                for (auto* cred : credentials_) {
                    if (_wcsicmp(cred->UserSid().c_str(), targetSid.c_str()) == 0) {
                        cred->SetPendingAttempt(attemptId);
                        lastNotifiedAttempt = attemptId;
                        if (providerEvents_) {
                            providerEvents_->CredentialsChanged(adviseContext_);
                        }
                        break;
                    }
                }
            }
        }
    }
    if (readyEv) CloseHandle(readyEv);
}

HRESULT CPhoneUnlockProvider::GetFieldDescriptorCount(DWORD* pdwCount) {
    if (!pdwCount) return E_INVALIDARG;
    *pdwCount = PFI_NUM_FIELDS;
    return S_OK;
}

HRESULT CPhoneUnlockProvider::GetFieldDescriptorAt(DWORD dwIndex, CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** ppcpfd) {
    if (!ppcpfd || dwIndex >= PFI_NUM_FIELDS) return E_INVALIDARG;
    *ppcpfd = static_cast<CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR*>(CoTaskMemAlloc(sizeof(CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR)));
    if (!*ppcpfd) return E_OUTOFMEMORY;
    **ppcpfd = kFieldDescriptors[dwIndex];
    if (kFieldDescriptors[dwIndex].pszLabel) {
        HRESULT hr = SHStrDupW(kFieldDescriptors[dwIndex].pszLabel, &(*ppcpfd)->pszLabel);
        if (FAILED(hr)) {
            CoTaskMemFree(*ppcpfd);
            *ppcpfd = nullptr;
            return hr;
        }
    }
    return S_OK;
}

void CPhoneUnlockProvider::ReleaseCredentials() {
    for (auto* c : credentials_) c->Release();
    credentials_.clear();
}

void CPhoneUnlockProvider::EnumerateCredentials() {
    if (!userArray_) return;
    DWORD count = 0;
    if (FAILED(userArray_->GetCount(&count)) || count == 0) return;

    for (DWORD i = 0; i < count; ++i) {
        ICredentialProviderUser* user = nullptr;
        if (SUCCEEDED(userArray_->GetAt(i, &user)) && user) {
            auto* cred = new (std::nothrow) CPhoneUnlockCredential(providerPipe_, allowedServerSid_);
            if (cred) {
                if (SUCCEEDED(cred->Initialize(cpus_, user))) {
                    credentials_.push_back(cred);
                } else {
                    cred->Release();
                }
            }
            user->Release();
        }
    }
}

HRESULT CPhoneUnlockProvider::AddTestUser(
    const std::wstring& userSid,
    const std::wstring& qualifiedUserName,
    bool isLocalUser) {
    recreateCredentials_ = false;
    auto* cred = new (std::nothrow) CPhoneUnlockCredential(providerPipe_, allowedServerSid_);
    if (!cred) return E_OUTOFMEMORY;
    cred->InitializeForTest(cpus_, userSid, qualifiedUserName, isLocalUser);
    credentials_.push_back(cred);
    return S_OK;
}

HRESULT CPhoneUnlockProvider::GetCredentialCount(
    DWORD* pdwCount,
    DWORD* pdwDefault,
    BOOL* pbAutoLogonWithDefault) {
    if (!pdwCount || !pdwDefault || !pbAutoLogonWithDefault) return E_INVALIDARG;
    *pdwDefault = CREDENTIAL_PROVIDER_NO_DEFAULT;
    *pbAutoLogonWithDefault = FALSE;

    if (recreateCredentials_) {
        recreateCredentials_ = false;
        ReleaseCredentials();
        EnumerateCredentials();
    }

    // Check if the service currently has a pending phone unlock attempt for any user tile.
    JsonWriter reqW;
    reqW.Str("op", "provider.poll");
    std::string respStr;
    if (PipeTransact(providerPipe_, reqW.Build(), respStr, /*requireSystemServer=*/true, allowedServerSid_, 600)) {
        JsonObject resp;
        if (JsonParseFlat(respStr, resp) && Get(resp, "ok") == "true" && Get(resp, "has_pending") == "true") {
            std::wstring targetSid = Utf8ToWide(Get(resp, "user_sid"));
            std::string attemptId = Get(resp, "attempt_id");
            for (DWORD i = 0; i < (DWORD)credentials_.size(); ++i) {
                if (_wcsicmp(credentials_[i]->UserSid().c_str(), targetSid.c_str()) == 0) {
                    credentials_[i]->SetPendingAttempt(attemptId);
                    break;
                }
            }
        }
    }

    for (DWORD i = 0; i < (DWORD)credentials_.size(); ++i) {
        if (credentials_[i]->ConsumeAutoLogonFlag()) {
            *pdwDefault = i;
            *pbAutoLogonWithDefault = TRUE;
            break;
        }
    }

    *pdwCount = static_cast<DWORD>(credentials_.size());
    return S_OK;
}

HRESULT CPhoneUnlockProvider::GetCredentialAt(DWORD dwIndex, ICredentialProviderCredential** ppcpc) {
    if (!ppcpc || dwIndex >= credentials_.size()) return E_INVALIDARG;
    return credentials_[dwIndex]->QueryInterface(IID_PPV_ARGS(ppcpc));
}

HRESULT CPhoneUnlockProvider::SetUserArray(ICredentialProviderUserArray* users) {
    if (userArray_) userArray_->Release();
    userArray_ = users;
    if (userArray_) userArray_->AddRef();
    return S_OK;
}

// ================================================================ ClassFactory + COM exports

class CClassFactory final : public IClassFactory {
public:
    CClassFactory() { DllAddRef(); }
    ~CClassFactory() { DllRelease(); }

    IFACEMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&refCount_); }
    IFACEMETHODIMP_(ULONG) Release() override {
        LONG c = InterlockedDecrement(&refCount_);
        if (!c) delete this;
        return c;
    }
    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_INVALIDARG;
        if (riid == IID_IUnknown || riid == IID_IClassFactory) {
            *ppv = static_cast<IClassFactory*>(this);
            AddRef();
            return S_OK;
        }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }
    IFACEMETHODIMP CreateInstance(IUnknown* pUnkOuter, REFIID riid, void** ppv) override {
        if (pUnkOuter) return CLASS_E_NOAGGREGATION;
        auto* p = new (std::nothrow) CPhoneUnlockProvider();
        if (!p) return E_OUTOFMEMORY;
        HRESULT hr = p->QueryInterface(riid, ppv);
        p->Release();
        return hr;
    }
    IFACEMETHODIMP LockServer(BOOL fLock) override {
        if (fLock) DllAddRef();
        else DllRelease();
        return S_OK;
    }

private:
    LONG refCount_ = 1;
};

}  // namespace pcpr

extern "C" BOOL WINAPI DllMain(HINSTANCE hInst, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        pcpr::g_hInstance = hInst;
        DisableThreadLibraryCalls(hInst);
    }
    return TRUE;
}

extern "C" HRESULT STDAPICALLTYPE DllCanUnloadNow() {
    return (pcpr::g_dllRefCount == 0) ? S_OK : S_FALSE;
}

extern "C" HRESULT STDAPICALLTYPE DllGetClassObject(REFCLSID rclsid, REFIID riid, void** ppv) {
    if (!ppv) return E_INVALIDARG;
    *ppv = nullptr;
    if (!IsEqualCLSID(rclsid, pcpr::CLSID_PhoneUnlockProvider)) return CLASS_E_CLASSNOTAVAILABLE;
    auto* cf = new (std::nothrow) pcpr::CClassFactory();
    if (!cf) return E_OUTOFMEMORY;
    HRESULT hr = cf->QueryInterface(riid, ppv);
    cf->Release();
    return hr;
}

extern "C" HRESULT STDAPICALLTYPE DllRegisterServer() {
    wchar_t dllPath[MAX_PATH * 2] = {};
    if (!GetModuleFileNameW(pcpr::g_hInstance, dllPath, MAX_PATH * 2)) return HRESULT_FROM_WIN32(GetLastError());

    std::wstring clsidKey = std::wstring(L"CLSID\\") + pcpr::kProviderClsidString;
    std::wstring inprocKey = clsidKey + L"\\InprocServer32";
    std::wstring cpKey = std::wstring(L"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Authentication\\Credential Providers\\") + pcpr::kProviderClsidString;

    HKEY hKey = nullptr;
    if (RegCreateKeyExW(HKEY_CLASSES_ROOT, clsidKey.c_str(), 0, nullptr, 0, KEY_WRITE, nullptr, &hKey, nullptr) != ERROR_SUCCESS)
        return E_ACCESSDENIED;
    const wchar_t* title = L"PCPhoneRemoteCredentialProvider";
    RegSetValueExW(hKey, nullptr, 0, REG_SZ, reinterpret_cast<const BYTE*>(title), (DWORD)((wcslen(title) + 1) * sizeof(wchar_t)));
    RegCloseKey(hKey);

    if (RegCreateKeyExW(HKEY_CLASSES_ROOT, inprocKey.c_str(), 0, nullptr, 0, KEY_WRITE, nullptr, &hKey, nullptr) != ERROR_SUCCESS)
        return E_ACCESSDENIED;
    RegSetValueExW(hKey, nullptr, 0, REG_SZ, reinterpret_cast<const BYTE*>(dllPath), (DWORD)((wcslen(dllPath) + 1) * sizeof(wchar_t)));
    const wchar_t* model = L"Apartment";
    RegSetValueExW(hKey, L"ThreadingModel", 0, REG_SZ, reinterpret_cast<const BYTE*>(model), (DWORD)((wcslen(model) + 1) * sizeof(wchar_t)));
    RegCloseKey(hKey);

    if (RegCreateKeyExW(HKEY_LOCAL_MACHINE, cpKey.c_str(), 0, nullptr, 0, KEY_WRITE, nullptr, &hKey, nullptr) != ERROR_SUCCESS)
        return E_ACCESSDENIED;
    RegSetValueExW(hKey, nullptr, 0, REG_SZ, reinterpret_cast<const BYTE*>(title), (DWORD)((wcslen(title) + 1) * sizeof(wchar_t)));
    RegCloseKey(hKey);
    return S_OK;
}

extern "C" HRESULT STDAPICALLTYPE DllUnregisterServer() {
    std::wstring clsidKey = std::wstring(L"CLSID\\") + pcpr::kProviderClsidString;
    std::wstring cpKey = std::wstring(L"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Authentication\\Credential Providers\\") + pcpr::kProviderClsidString;
    RegDeleteTreeW(HKEY_LOCAL_MACHINE, cpKey.c_str());
    RegDeleteTreeW(HKEY_CLASSES_ROOT, clsidKey.c_str());
    return S_OK;
}
