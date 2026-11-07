#include "unlock_engine.h"

#include <iostream>

namespace {

constexpr const wchar_t* kServiceName = L"PCPhoneRemoteUnlock";
constexpr const wchar_t* kServiceDisplay = L"PC Phone Remote - Windows Unlock Service";

SERVICE_STATUS_HANDLE g_statusHandle = nullptr;
SERVICE_STATUS g_status = {};
pcpr::UnlockEngine* g_engine = nullptr;
HANDLE g_stopEvent = nullptr;

void ReportServiceState(DWORD state, DWORD exitCode = NO_ERROR, DWORD waitHint = 0) {
    if (!g_statusHandle) return;
    static DWORD checkPoint = 1;
    g_status.dwCurrentState = state;
    g_status.dwWin32ExitCode = exitCode;
    g_status.dwWaitHint = waitHint;
    g_status.dwControlsAccepted = (state == SERVICE_START_PENDING) ? 0 : (SERVICE_ACCEPT_STOP | SERVICE_ACCEPT_SHUTDOWN);
    g_status.dwCheckPoint = (state == SERVICE_RUNNING || state == SERVICE_STOPPED) ? 0 : checkPoint++;
    SetServiceStatus(g_statusHandle, &g_status);
}

DWORD WINAPI ServiceCtrlHandler(DWORD control, DWORD, LPVOID, LPVOID) {
    switch (control) {
    case SERVICE_CONTROL_STOP:
    case SERVICE_CONTROL_SHUTDOWN:
        ReportServiceState(SERVICE_STOP_PENDING, NO_ERROR, 3000);
        if (g_stopEvent) SetEvent(g_stopEvent);
        return NO_ERROR;
    case SERVICE_CONTROL_INTERROGATE:
        return NO_ERROR;
    default:
        return ERROR_CALL_NOT_IMPLEMENTED;
    }
}

void WINAPI ServiceMain(DWORD, LPWSTR*) {
    g_status.dwServiceType = SERVICE_WIN32_OWN_PROCESS;
    g_statusHandle = RegisterServiceCtrlHandlerExW(kServiceName, ServiceCtrlHandler, nullptr);
    if (!g_statusHandle) return;

    ReportServiceState(SERVICE_START_PENDING, NO_ERROR, 3000);
    g_stopEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);

    pcpr::EngineConfig cfg;
    pcpr::UnlockEngine engine(cfg);
    g_engine = &engine;
    if (!engine.Start()) {
        ReportServiceState(SERVICE_STOPPED, ERROR_SERVICE_SPECIFIC_ERROR);
        CloseHandle(g_stopEvent);
        return;
    }

    ReportServiceState(SERVICE_RUNNING);
    WaitForSingleObject(g_stopEvent, INFINITE);
    engine.Stop();
    g_engine = nullptr;
    CloseHandle(g_stopEvent);
    ReportServiceState(SERVICE_STOPPED);
}

int InstallService() {
    wchar_t exePath[MAX_PATH * 2] = {};
    if (!GetModuleFileNameW(nullptr, exePath, MAX_PATH * 2)) return 1;
    std::wstring cmd = L"\"" + std::wstring(exePath) + L"\" --service";

    SC_HANDLE scm = OpenSCManagerW(nullptr, nullptr, SC_MANAGER_CREATE_SERVICE);
    if (!scm) {
        std::wcerr << L"OpenSCManager failed (run as Administrator): " << GetLastError() << L"\n";
        return 1;
    }
    SC_HANDLE svc = CreateServiceW(
        scm,
        kServiceName,
        kServiceDisplay,
        SERVICE_ALL_ACCESS,
        SERVICE_WIN32_OWN_PROCESS,
        SERVICE_AUTO_START,
        SERVICE_ERROR_NORMAL,
        cmd.c_str(),
        nullptr, nullptr, nullptr,
        nullptr,
        nullptr);
    if (!svc && GetLastError() == ERROR_SERVICE_EXISTS) {
        svc = OpenServiceW(scm, kServiceName, SERVICE_ALL_ACCESS);
    }
    if (!svc) {
        std::wcerr << L"CreateService failed: " << GetLastError() << L"\n";
        CloseServiceHandle(scm);
        return 1;
    }
    StartServiceW(svc, 0, nullptr);
    CloseServiceHandle(svc);
    CloseServiceHandle(scm);
    std::wcout << L"Service installed and started.\n";
    return 0;
}

int UninstallService() {
    SC_HANDLE scm = OpenSCManagerW(nullptr, nullptr, SC_MANAGER_CONNECT);
    if (!scm) return 1;
    SC_HANDLE svc = OpenServiceW(scm, kServiceName, SERVICE_STOP | DELETE);
    if (svc) {
        SERVICE_STATUS st = {};
        ControlService(svc, SERVICE_CONTROL_STOP, &st);
        DeleteService(svc);
        CloseServiceHandle(svc);
    }
    CloseServiceHandle(scm);
    std::wcout << L"Service removed.\n";
    return 0;
}

}  // namespace

int wmain(int argc, wchar_t* argv[]) {
    pcpr::EngineConfig cfg;
    bool runConsole = false;

    for (int i = 1; i < argc; ++i) {
        std::wstring arg = argv[i];
        if (arg == L"--install") return InstallService();
        if (arg == L"--uninstall") return UninstallService();
        if (arg == L"--console") runConsole = true;
        else if (arg == L"--state-dir" && i + 1 < argc) cfg.stateDir = argv[++i];
        else if (arg == L"--control-pipe" && i + 1 < argc) cfg.controlPipe = argv[++i];
        else if (arg == L"--provider-pipe" && i + 1 < argc) cfg.providerPipe = argv[++i];
        else if (arg == L"--allow-test-peer") {
            cfg.allowTestPeer = true;
            std::wstring q;
            pcpr::GetCurrentProcessUser(cfg.testOwnerSid, q);
        }
        else if (arg == L"--allow-synthetic-logon") cfg.allowSyntheticLogon = true;
    }

    if (runConsole) {
        pcpr::UnlockEngine engine(cfg);
        if (!engine.Start()) {
            std::wcerr << L"Failed to start UnlockEngine.\n";
            return 1;
        }
        std::wcout << L"PhoneUnlockService running in console mode on " << cfg.controlPipe << L"\n";
        g_stopEvent = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        SetConsoleCtrlHandler([](DWORD) -> BOOL {
            if (g_stopEvent) SetEvent(g_stopEvent);
            return TRUE;
        }, TRUE);
        WaitForSingleObject(g_stopEvent, INFINITE);
        engine.Stop();
        CloseHandle(g_stopEvent);
        return 0;
    }

    SERVICE_TABLE_ENTRYW table[] = {
        {const_cast<LPWSTR>(kServiceName), ServiceMain},
        {nullptr, nullptr}
    };
    if (!StartServiceCtrlDispatcherW(table)) {
        // If invoked interactively without flags, fall back to console mode so developers can inspect logs.
        if (GetLastError() == ERROR_FAILED_SERVICE_CONTROLLER_CONNECT) {
            std::wcout << L"Starting in console mode (use --service when launched by SCM).\n";
            pcpr::UnlockEngine engine(cfg);
            if (!engine.Start()) return 1;
            Sleep(INFINITE);
        }
        return 1;
    }
    return 0;
}
