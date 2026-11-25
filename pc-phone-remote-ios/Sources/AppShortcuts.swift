import AppIntents
import Foundation

private final class NoRedirectDelegate: NSObject, URLSessionTaskDelegate {
    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse,
        newRequest request: URLRequest,
        completionHandler: @escaping (URLRequest?) -> Void
    ) {
        completionHandler(nil)
    }
}

private enum ShortcutRunner {
    private static let noRedirectDelegate = NoRedirectDelegate()

    static func activeProfile() -> DeviceProfile? {
        guard let data = UserDefaults.standard.data(forKey: "pcpr_ios_profiles"),
              let profiles = try? JSONDecoder().decode([DeviceProfile].self, from: data),
              !profiles.isEmpty
        else { return nil }
        let idx = UserDefaults.standard.integer(forKey: "pcpr_ios_selected_idx")
        return profiles[max(0, min(idx, profiles.count - 1))]
    }

    static func send(_ payload: [String: Any]) async throws -> String {
        guard let profile = activeProfile() else {
            return "Open PC Remote and add your PC first."
        }
        guard let loginUrl = URL(string: "\(profile.baseURL)/login"),
              let apiUrl = URL(string: "\(profile.baseURL)/api/v2")
        else {
            return "Invalid PC address."
        }

        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = 6
        let session = URLSession(configuration: cfg, delegate: noRedirectDelegate, delegateQueue: nil)

        var loginReq = URLRequest(url: loginUrl)
        loginReq.httpMethod = "POST"
        loginReq.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        let encodedPin = profile.pin.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? profile.pin
        loginReq.httpBody = Data("pin=\(encodedPin)".utf8)

        let (_, loginResp) = try await session.data(for: loginReq)
        guard let httpLogin = loginResp as? HTTPURLResponse,
              httpLogin.statusCode == 303 || httpLogin.statusCode == 200
        else {
            return "Failed to authenticate with \(profile.name)."
        }
        let cookie = (httpLogin.value(forHTTPHeaderField: "Set-Cookie") ?? "")
            .split(separator: ";").first.map(String.init) ?? ""

        var apiReq = URLRequest(url: apiUrl)
        apiReq.httpMethod = "POST"
        apiReq.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if !cookie.isEmpty {
            apiReq.setValue(cookie, forHTTPHeaderField: "Cookie")
        }
        apiReq.httpBody = try JSONSerialization.data(withJSONObject: payload)

        let (_, apiResp) = try await session.data(for: apiReq)
        guard let httpApi = apiResp as? HTTPURLResponse, (200...299).contains(httpApi.statusCode) else {
            return "Command rejected by \(profile.name)."
        }
        return "Sent to \(profile.name)."
    }
}

struct LockPCIntent: AppIntent {
    static var title: LocalizedStringResource = "Lock PC"
    static var description = IntentDescription("Lock your active Windows or Linux PC.")

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let msg = try await ShortcutRunner.send(["action": "command", "command": "lock"])
        return .result(dialog: IntentDialog(stringLiteral: msg))
    }
}

struct SleepPCIntent: AppIntent {
    static var title: LocalizedStringResource = "Sleep PC"
    static var description = IntentDescription("Put your active PC to sleep.")

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let msg = try await ShortcutRunner.send(["action": "command", "command": "sleep"])
        return .result(dialog: IntentDialog(stringLiteral: msg))
    }
}

struct ScreenOffPCIntent: AppIntent {
    static var title: LocalizedStringResource = "Turn Off PC Screen"
    static var description = IntentDescription("Turn off the monitor without putting the PC to sleep.")

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let msg = try await ShortcutRunner.send(["action": "display.off"])
        return .result(dialog: IntentDialog(stringLiteral: msg))
    }
}

struct ToggleMutePCIntent: AppIntent {
    static var title: LocalizedStringResource = "Mute PC"
    static var description = IntentDescription("Toggle mute on your active PC.")

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let msg = try await ShortcutRunner.send(["action": "media", "key": "mute"])
        return .result(dialog: IntentDialog(stringLiteral: msg))
    }
}

struct PlayPausePCIntent: AppIntent {
    static var title: LocalizedStringResource = "Play or Pause Media on PC"
    static var description = IntentDescription("Toggle media playback on your active PC.")

    func perform() async throws -> some IntentResult & ProvidesDialog {
        let msg = try await ShortcutRunner.send(["action": "media", "key": "play_pause"])
        return .result(dialog: IntentDialog(stringLiteral: msg))
    }
}

struct PCPhoneRemoteShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: LockPCIntent(),
            phrases: ["Lock my PC with \(.applicationName)", "Lock computer in \(.applicationName)"],
            shortTitle: "Lock PC",
            systemImageName: "lock.fill"
        )
        AppShortcut(
            intent: SleepPCIntent(),
            phrases: ["Put my PC to sleep with \(.applicationName)", "Sleep PC in \(.applicationName)"],
            shortTitle: "Sleep PC",
            systemImageName: "moon.fill"
        )
        AppShortcut(
            intent: ScreenOffPCIntent(),
            phrases: ["Turn off PC screen with \(.applicationName)"],
            shortTitle: "Screen Off",
            systemImageName: "display"
        )
        AppShortcut(
            intent: ToggleMutePCIntent(),
            phrases: ["Mute my PC with \(.applicationName)"],
            shortTitle: "Mute PC",
            systemImageName: "speaker.slash.fill"
        )
        AppShortcut(
            intent: PlayPausePCIntent(),
            phrases: ["Play or pause PC in \(.applicationName)"],
            shortTitle: "Play / Pause",
            systemImageName: "playpause.fill"
        )
    }
}
