// Windows Credential Provider v2 for PC Phone Remote.
// Derived from Microsoft's Credential Provider v2 sample architecture, retaining all standard
// system credential providers and validating credentials through Windows LSA / Kerberos.
#pragma once

#ifndef WIN32_NO_STATUS
#include <ntstatus.h>
#define WIN32_NO_STATUS
#endif
#include <windows.h>
#include <unknwn.h>
#include <credentialprovider.h>
#include <ntsecapi.h>
#define SECURITY_WIN32
#include <security.h>
#include <shlguid.h>
#include <propkey.h>
#include <shlwapi.h>
#include <strsafe.h>
#include <wincred.h>

#include "../common/ipc.h"
#include "../common/util.h"

#include <atomic>
#include <string>
#include <thread>
#include <vector>

namespace pcpr {

// {D7F4C9E2-54C9-4E6D-9B0C-48E71F6A8C21}
extern const CLSID CLSID_PhoneUnlockProvider;

enum PHONE_FIELD_ID {
    PFI_TILEIMAGE = 0,
    PFI_LABEL = 1,
    PFI_LARGE_TEXT = 2,
    PFI_SMALL_TEXT = 3,
    PFI_SUBMIT_BUTTON = 4,
    PFI_NUM_FIELDS = 5,
};

void DllAddRef();
void DllRelease();

class CPhoneUnlockCredential final : public ICredentialProviderCredential2,
                                     public ICredentialProviderCredentialWithFieldOptions {
public:
    explicit CPhoneUnlockCredential(
        const std::wstring& providerPipe = kProviderPipeName,
        const std::wstring& allowedServerSid = L"");
    ~CPhoneUnlockCredential();

    // IUnknown
    IFACEMETHODIMP_(ULONG) AddRef() override;
    IFACEMETHODIMP_(ULONG) Release() override;
    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) override;

    // ICredentialProviderCredential
    IFACEMETHODIMP Advise(ICredentialProviderCredentialEvents* pcpce) override;
    IFACEMETHODIMP UnAdvise() override;
    IFACEMETHODIMP SetSelected(BOOL* pbAutoLogon) override;
    IFACEMETHODIMP SetDeselected() override;
    IFACEMETHODIMP GetFieldState(DWORD dwFieldID, CREDENTIAL_PROVIDER_FIELD_STATE* pcpfs, CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE* pcpfis) override;
    IFACEMETHODIMP GetStringValue(DWORD dwFieldID, PWSTR* ppwsz) override;
    IFACEMETHODIMP GetBitmapValue(DWORD dwFieldID, HBITMAP* phbmp) override;
    IFACEMETHODIMP GetCheckboxValue(DWORD dwFieldID, BOOL* pbChecked, PWSTR* ppwszLabel) override;
    IFACEMETHODIMP GetSubmitButtonValue(DWORD dwFieldID, DWORD* pdwAdjacentTo) override;
    IFACEMETHODIMP GetComboBoxValueCount(DWORD dwFieldID, DWORD* pcItems, DWORD* pdwSelectedItem) override;
    IFACEMETHODIMP GetComboBoxValueAt(DWORD dwFieldID, DWORD dwItem, PWSTR* ppwszItem) override;
    IFACEMETHODIMP SetStringValue(DWORD dwFieldID, PCWSTR pwz) override;
    IFACEMETHODIMP SetCheckboxValue(DWORD dwFieldID, BOOL bChecked) override;
    IFACEMETHODIMP SetComboBoxSelectedValue(DWORD dwFieldID, DWORD dwSelectedItem) override;
    IFACEMETHODIMP CommandLinkClicked(DWORD dwFieldID) override;
    IFACEMETHODIMP GetSerialization(
        CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE* pcpgsr,
        CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs,
        PWSTR* ppwszOptionalStatusText,
        CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon) override;
    IFACEMETHODIMP ReportResult(
        NTSTATUS ntsStatus,
        NTSTATUS ntsSubstatus,
        PWSTR* ppwszOptionalStatusText,
        CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon) override;

    // ICredentialProviderCredential2
    IFACEMETHODIMP GetUserSid(PWSTR* ppszSid) override;

    // ICredentialProviderCredentialWithFieldOptions
    IFACEMETHODIMP GetFieldOptions(DWORD dwFieldID, CREDENTIAL_PROVIDER_CREDENTIAL_FIELD_OPTIONS* pcpcfo) override;

    HRESULT Initialize(
        CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus,
        ICredentialProviderUser* pcpUser);

    // Direct initialization used by the automated self-test harness.
    HRESULT InitializeForTest(
        CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus,
        const std::wstring& userSid,
        const std::wstring& qualifiedUserName,
        bool isLocalUser = true);

    const std::wstring& UserSid() const { return userSid_; }
    void SetPendingAttempt(const std::string& attemptId);
    bool ConsumeAutoLogonFlag();

private:
    LONG refCount_ = 1;
    CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus_ = CPUS_INVALID;
    std::wstring providerPipe_;
    std::wstring allowedServerSid_;
    std::wstring userSid_;
    std::wstring qualifiedUser_;
    bool isLocalUser_ = true;
    std::string lastAttemptId_;
    std::atomic<bool> pendingAutoLogon_{false};
    ICredentialProviderCredentialEvents* events_ = nullptr;
};

class CPhoneUnlockProvider final : public ICredentialProvider,
                                   public ICredentialProviderSetUserArray {
public:
    explicit CPhoneUnlockProvider(
        const std::wstring& providerPipe = kProviderPipeName,
        const std::wstring& readyEventName = kReadyEventName,
        const std::wstring& allowedServerSid = L"");
    ~CPhoneUnlockProvider();

    // IUnknown
    IFACEMETHODIMP_(ULONG) AddRef() override;
    IFACEMETHODIMP_(ULONG) Release() override;
    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) override;

    // ICredentialProvider
    IFACEMETHODIMP SetUsageScenario(CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus, DWORD dwFlags) override;
    IFACEMETHODIMP SetSerialization(const CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs) override;
    IFACEMETHODIMP Advise(ICredentialProviderEvents* pcpe, UINT_PTR upAdviseContext) override;
    IFACEMETHODIMP UnAdvise() override;
    IFACEMETHODIMP GetFieldDescriptorCount(DWORD* pdwCount) override;
    IFACEMETHODIMP GetFieldDescriptorAt(DWORD dwIndex, CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** ppcpfd) override;
    IFACEMETHODIMP GetCredentialCount(DWORD* pdwCount, DWORD* pdwDefault, BOOL* pbAutoLogonWithDefault) override;
    IFACEMETHODIMP GetCredentialAt(DWORD dwIndex, ICredentialProviderCredential** ppcpc) override;

    // ICredentialProviderSetUserArray
    IFACEMETHODIMP SetUserArray(ICredentialProviderUserArray* users) override;

    // Test helper to populate a user tile without LogonUI's ICredentialProviderUserArray.
    HRESULT AddTestUser(const std::wstring& userSid, const std::wstring& qualifiedUserName, bool isLocalUser = true);

private:
    void ReleaseCredentials();
    void EnumerateCredentials();
    void WatcherLoop();

    LONG refCount_ = 1;
    CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus_ = CPUS_INVALID;
    std::wstring providerPipe_;
    std::wstring readyEventName_;
    std::wstring allowedServerSid_;
    bool recreateCredentials_ = false;
    ICredentialProviderUserArray* userArray_ = nullptr;
    ICredentialProviderEvents* providerEvents_ = nullptr;
    UINT_PTR adviseContext_ = 0;
    std::vector<CPhoneUnlockCredential*> credentials_;

    std::atomic<bool> watching_{false};
    HANDLE stopWatchEvent_ = nullptr;
    std::thread watcherThread_;
};

}  // namespace pcpr
