import Darwin
import Combine
import Foundation

struct DeviceProfile: Identifiable, Codable, Equatable {
    var id: String = UUID().uuidString
    var name: String
    var host: String
    var port: String = "8765"
    var pin: String
    var mac: String = ""

    var baseURL: String {
        let clean = host.trimmingCharacters(in: .whitespacesAndNewlines)
        if clean.hasPrefix("http://") || clean.hasPrefix("https://") {
            return clean.hasSuffix("/") ? String(clean.dropLast()) : clean
        }
        return "http://\(clean):\(port.isEmpty ? "8765" : port)"
    }
}

struct DiscoveredPC: Identifiable, Hashable {
    let name: String
    let host: String
    let port: Int
    let mac: String
    let os: String

    var id: String { "\(host):\(port)" }
}

struct SharedFileEntry: Identifiable {
    let name: String
    let size: Int64
    var id: String { name }
}

private final class NoRedirectSessionDelegate: NSObject, URLSessionTaskDelegate {
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

enum RemoteError: LocalizedError {
    case invalidAddress
    case authFailed(String)
    case serverError(String)

    var errorDescription: String? {
        switch self {
        case .invalidAddress: return "Invalid host or port."
        case .authFailed(let msg): return msg
        case .serverError(let msg): return msg
        }
    }
}

@MainActor
final class AppStore: ObservableObject {
    private static let profilesKey = "pcpr_ios_profiles"
    private static let selectedKey = "pcpr_ios_selected_idx"
    private static let tourKey = "pcpr_ios_tour_done_v1"
    private static let tipsKey = "pcpr_ios_dismissed_tips"

    @Published var profiles: [DeviceProfile] = []
    @Published var selectedIndex: Int = 0
    @Published var currentTab: Int = 0
    @Published var statusData: [String: Any] = [:]
    @Published var sharedFiles: [SharedFileEntry] = []
    @Published var clipboardText: String = ""
    @Published var bannerMessage: String = "Ready"
    @Published var bannerIsError: Bool = false
    @Published var showOnboardingTour: Bool = false
    @Published var dismissedTips: Set<String> = []
    @Published var discoveredPCs: [DiscoveredPC] = []
    @Published var isScanning: Bool = false
    @Published var pendingEnrollUri: ParsedEnrollUri?
    @Published var customButtons: [[String: String]] = []
    @Published var processes: [[String: Any]] = []
    @Published var audioDevices: [[String: Any]] = []
    @Published var audioSessions: [[String: Any]] = []
    @Published var brightnessPercent: Double = 80
    @Published var brightnessSupported: Bool = false

    private var cookiesByProfile: [String: String] = [:]
    private let redirectDelegate = NoRedirectSessionDelegate()
    private lazy var session: URLSession = {
        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest = 6
        cfg.timeoutIntervalForResource = 12
        return URLSession(configuration: cfg, delegate: redirectDelegate, delegateQueue: nil)
    }()

    init() {
        if let data = UserDefaults.standard.data(forKey: Self.profilesKey),
           let decoded = try? JSONDecoder().decode([DeviceProfile].self, from: data)
        {
            profiles = decoded
        }
        selectedIndex = UserDefaults.standard.integer(forKey: Self.selectedKey)
        if !profiles.isEmpty {
            selectedIndex = max(0, min(selectedIndex, profiles.count - 1))
        } else {
            selectedIndex = 0
            currentTab = 3
        }
        showOnboardingTour = !UserDefaults.standard.bool(forKey: Self.tourKey)
        dismissedTips = Set(UserDefaults.standard.stringArray(forKey: Self.tipsKey) ?? [])
    }

    var activeProfile: DeviceProfile? {
        guard selectedIndex >= 0, selectedIndex < profiles.count else { return nil }
        return profiles[selectedIndex]
    }

    func persistProfiles() {
        if let encoded = try? JSONEncoder().encode(profiles) {
            UserDefaults.standard.set(encoded, forKey: Self.profilesKey)
        }
        UserDefaults.standard.set(selectedIndex, forKey: Self.selectedKey)
    }

    func addOrUpdateProfile(_ profile: DeviceProfile) {
        if let idx = profiles.firstIndex(where: { $0.id == profile.id }) {
            profiles[idx] = profile
            cookiesByProfile.removeValue(forKey: profile.id)
        } else {
            profiles.append(profile)
            selectedIndex = profiles.count - 1
        }
        persistProfiles()
    }

    func deleteProfile(id: String) {
        profiles.removeAll { $0.id == id }
        cookiesByProfile.removeValue(forKey: id)
        UnlockCrypto.clearEnrollment(profileId: id)
        selectedIndex = profiles.isEmpty ? 0 : max(0, min(selectedIndex, profiles.count - 1))
        persistProfiles()
    }

    func dismissTip(_ key: String) {
        dismissedTips.insert(key)
        UserDefaults.standard.set(Array(dismissedTips), forKey: Self.tipsKey)
    }

    func completeTour() {
        showOnboardingTour = false
        UserDefaults.standard.set(true, forKey: Self.tourKey)
    }

    func replayTour() {
        dismissedTips.removeAll()
        UserDefaults.standard.removeObject(forKey: Self.tipsKey)
        UserDefaults.standard.set(false, forKey: Self.tourKey)
        showOnboardingTour = true
    }

    private func setBanner(_ message: String, isError: Bool = false) {
        bannerMessage = message
        bannerIsError = isError
    }

    private func login(profile: DeviceProfile) async throws -> String {
        guard let url = URL(string: "\(profile.baseURL)/login") else {
            throw RemoteError.invalidAddress
        }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        let encodedPin = profile.pin.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? profile.pin
        req.httpBody = Data("pin=\(encodedPin)".utf8)

        let (_, resp) = try await session.data(for: req)
        guard let http = resp as? HTTPURLResponse else {
            throw RemoteError.authFailed("No HTTP response")
        }
        if http.statusCode == 429 {
            throw RemoteError.authFailed("Too many failed attempts")
        }
        guard http.statusCode == 303,
              let rawCookie = http.value(forHTTPHeaderField: "Set-Cookie")
        else {
            throw RemoteError.authFailed("Wrong PC PIN or rejected login")
        }
        let cookiePair = rawCookie.split(separator: ";").first.map(String.init) ?? ""
        cookiesByProfile[profile.id] = cookiePair
        return cookiePair
    }

    @discardableResult
    func callAction(profile: DeviceProfile, payload: [String: Any]) async throws -> [String: Any] {
        guard let url = URL(string: "\(profile.baseURL)/api/v2") else {
            throw RemoteError.invalidAddress
        }
        let bodyData = try JSONSerialization.data(withJSONObject: payload)

        for attempt in 0..<2 {
            let cookie: String
            if let existing = cookiesByProfile[profile.id], attempt == 0 {
                cookie = existing
            } else {
                cookie = try await login(profile: profile)
            }

            var req = URLRequest(url: url)
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            if !cookie.isEmpty {
                req.setValue(cookie, forHTTPHeaderField: "Cookie")
            }
            req.httpBody = bodyData

            let (data, resp) = try await session.data(for: req)
            guard let http = resp as? HTTPURLResponse else {
                throw RemoteError.serverError("Connection failed")
            }
            if http.statusCode == 401 && attempt == 0 {
                cookiesByProfile.removeValue(forKey: profile.id)
                continue
            }
            let obj = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
            if !(200...299).contains(http.statusCode) {
                let msg = (obj["message"] as? String) ?? (obj["error"] as? String) ?? "HTTP \(http.statusCode)"
                throw RemoteError.serverError(msg)
            }
            return obj
        }
        throw RemoteError.authFailed("Session expired")
    }

    func performCommand(_ payload: [String: Any], successNote: String? = nil) {
        guard let profile = activeProfile else { return }
        Task {
            do {
                let res = try await callAction(profile: profile, payload: payload)
                if let msg = successNote ?? (res["message"] as? String), !msg.isEmpty {
                    setBanner(msg)
                }
                if payload["action"] as? String != "touchpad" {
                    await refreshStatus()
                }
            } catch {
                setBanner(error.localizedDescription, isError: true)
            }
        }
    }

    func refreshStatus() async {
        guard let profile = activeProfile else { return }
        do {
            let res = try await callAction(profile: profile, payload: ["action": "status"])
            statusData = res
            if let mac = res["mac"] as? String, !mac.isEmpty, profile.mac != mac,
               let idx = profiles.firstIndex(where: { $0.id == profile.id })
            {
                profiles[idx].mac = mac
                persistProfiles()
            }
            setBanner("Connected to \(profile.name)")
        } catch {
            setBanner(error.localizedDescription, isError: true)
        }
    }

    func refreshFiles() async {
        guard let profile = activeProfile else { return }
        do {
            let res = try await callAction(profile: profile, payload: ["action": "files.list"])
            let items = (res["files"] as? [[String: Any]]) ?? []
            sharedFiles = items.compactMap { row in
                guard let name = row["name"] as? String else { return nil }
                let size = (row["size"] as? NSNumber)?.int64Value ?? 0
                return SharedFileEntry(name: name, size: size)
            }
        } catch {
            setBanner(error.localizedDescription, isError: true)
        }
    }

    func uploadFile(url: URL) {
        guard let profile = activeProfile else { return }
        Task {
            let needsStop = url.startAccessingSecurityScopedResource()
            defer { if needsStop { url.stopAccessingSecurityScopedResource() } }
            do {
                let data = try Data(contentsOf: url)
                let res = try await callAction(profile: profile, payload: [
                    "action": "files.put",
                    "name": url.lastPathComponent,
                    "data": data.base64EncodedString(),
                ])
                setBanner((res["message"] as? String) ?? "File uploaded")
                await refreshFiles()
            } catch {
                setBanner(error.localizedDescription, isError: true)
            }
        }
    }

    func refreshCustomButtons() async {
        guard let profile = activeProfile else { return }
        if let res = try? await callAction(profile: profile, payload: ["action": "deck.custom_list"]),
           let raw = res["buttons"] as? [[String: Any]]
        {
            customButtons = raw.map { item in
                [
                    "id": String(describing: item["id"] ?? ""),
                    "label": String(describing: item["label"] ?? ""),
                    "icon": String(describing: item["icon"] ?? "⚡"),
                    "kind": String(describing: item["kind"] ?? "hotkey"),
                ]
            }
        }
    }

    func refreshProcesses() async {
        guard let profile = activeProfile else { return }
        if let res = try? await callAction(profile: profile, payload: ["action": "processes.list"]),
           let raw = res["processes"] as? [[String: Any]]
        {
            processes = raw
        }
    }

    func refreshAudio() async {
        guard let profile = activeProfile else { return }
        if let res = try? await callAction(profile: profile, payload: ["action": "audio.list"]) {
            audioDevices = (res["devices"] as? [[String: Any]]) ?? []
            audioSessions = (res["sessions"] as? [[String: Any]]) ?? []
        }
    }

    func refreshBrightness() async {
        guard let profile = activeProfile else { return }
        if let res = try? await callAction(profile: profile, payload: ["action": "display.status"]) {
            let sup = (res["supported"] as? Bool) ?? false
            brightnessSupported = sup
            if let b = (res["brightness"] as? NSNumber)?.doubleValue {
                brightnessPercent = b
            }
        }
    }

    func sendTouchpad(op: String, dx: Int = 0, dy: Int = 0, button: String = "left") {
        guard let profile = activeProfile else { return }
        Task {
            _ = try? await callAction(profile: profile, payload: [
                "action": "touchpad",
                "op": op,
                "dx": dx,
                "dy": dy,
                "button": button,
            ])
        }
    }

    func wakePc(_ profile: DeviceProfile) {
        let mac = profile.mac.isEmpty ? (statusData["mac"] as? String ?? "") : profile.mac
        Task.detached {
            Self.sendMagicPacket(macString: mac, hostHint: profile.host)
        }
        setBanner("Wake-on-LAN packet sent")
    }

    func scanLAN() {
        isScanning = true
        discoveredPCs = []
        Task.detached {
            let pcs = Self.discoverLocalPCs(timeoutMs: 1800)
            await MainActor.run {
                self.discoveredPCs = pcs
                self.isScanning = false
            }
        }
    }

    func handleIncomingURL(_ url: URL) {
        if let parsed = UnlockCrypto.parseEnrollCode(url.absoluteString) {
            if !parsed.host.isEmpty, !parsed.pin.isEmpty {
                let existing = profiles.first { $0.host == parsed.host && $0.port == parsed.port }
                if existing == nil {
                    addOrUpdateProfile(DeviceProfile(
                        name: parsed.pcName,
                        host: parsed.host,
                        port: parsed.port,
                        pin: parsed.pin
                    ))
                }
            }
            pendingEnrollUri = parsed
            currentTab = 0
            return
        }

        if let comp = URLComponents(url: url, resolvingAgainstBaseURL: false),
           (comp.scheme == "pcphone" && comp.host == "add") || ((comp.scheme == "http" || comp.scheme == "https") && comp.path.hasPrefix("/app"))
        {
            let params = Dictionary(
                (comp.queryItems ?? []).map { ($0.name, $0.value ?? "") },
                uniquingKeysWith: { first, _ in first }
            )
            let rawHost = params["host"] ?? comp.host ?? ""
            let pin = params["pin"] ?? ""
            guard !rawHost.isEmpty, !pin.isEmpty else { return }
            let finalHost = comp.scheme == "https" ? "https://\(rawHost):\(params["port"] ?? "8765")" : rawHost
            addOrUpdateProfile(DeviceProfile(
                name: params["name"]?.isEmpty == false ? params["name"]! : "PC",
                host: finalHost,
                port: params["port"]?.isEmpty == false ? params["port"]! : "8765",
                pin: pin,
                mac: params["mac"] ?? ""
            ))
            currentTab = 0
            Task { await refreshStatus() }
        }
    }

    // MARK: - POSIX UDP LAN Discovery + /api/discover fallback
    nonisolated private static func localIPv4Interfaces() -> [(ip: String, broadcast: String)] {
        var out: [(String, String)] = []
        var ifaddrPtr: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifaddrPtr) == 0, let first = ifaddrPtr else { return out }
        defer { freeifaddrs(ifaddrPtr) }

        var ptr: UnsafeMutablePointer<ifaddrs>? = first
        while let cur = ptr {
            defer { ptr = cur.pointee.ifa_next }
            guard let addr = cur.pointee.ifa_addr, addr.pointee.sa_family == UInt8(AF_INET) else { continue }
            let flags = Int32(cur.pointee.ifa_flags)
            guard (flags & IFF_UP) != 0, (flags & IFF_LOOPBACK) == 0 else { continue }

            var hostBuf = [CChar](repeating: 0, count: Int(NI_MAXHOST))
            getnameinfo(addr, socklen_t(addr.pointee.sa_len), &hostBuf, socklen_t(hostBuf.count), nil, 0, NI_NUMERICHOST)
            let ip = String(cString: hostBuf)
            var bcast = "255.255.255.255"
            if let dst = cur.pointee.ifa_dstaddr, dst.pointee.sa_family == UInt8(AF_INET) {
                var bcastBuf = [CChar](repeating: 0, count: Int(NI_MAXHOST))
                getnameinfo(dst, socklen_t(dst.pointee.sa_len), &bcastBuf, socklen_t(bcastBuf.count), nil, 0, NI_NUMERICHOST)
                let candidate = String(cString: bcastBuf)
                if !candidate.isEmpty { bcast = candidate }
            }
            out.append((ip, bcast))
        }
        return out
    }

    nonisolated private static func discoverLocalPCs(timeoutMs: Int) -> [DiscoveredPC] {
        var found: [String: DiscoveredPC] = [:]
        let ifaces = localIPv4Interfaces()
        var targets = Set(["255.255.255.255"])
        for entry in ifaces { targets.insert(entry.broadcast) }

        let fd = Darwin.socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
        if fd >= 0 {
            defer { Darwin.close(fd) }
            var yes: Int32 = 1
            setsockopt(fd, SOL_SOCKET, SO_BROADCAST, &yes, socklen_t(MemoryLayout<Int32>.size))
            var tv = timeval(tv_sec: 0, tv_usec: 350_000)
            setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, socklen_t(MemoryLayout<timeval>.size))

            let probe = Array("PCPHONE_DISCOVER".utf8)
            for target in targets {
                var addr = sockaddr_in()
                addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
                addr.sin_family = sa_family_t(AF_INET)
                addr.sin_port = UInt16(8766).bigEndian
                if inet_pton(AF_INET, target, &addr.sin_addr) == 1 {
                    withUnsafePointer(to: &addr) { ptr in
                        ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sa in
                            _ = probe.withUnsafeBytes { buf in
                                Darwin.sendto(fd, buf.baseAddress, buf.count, 0, sa, socklen_t(MemoryLayout<sockaddr_in>.size))
                            }
                        }
                    }
                }
            }

            let deadline = Date().addingTimeInterval(Double(timeoutMs) / 1000.0)
            var recvBuf = [UInt8](repeating: 0, count: 4096)
            while Date() < deadline {
                var sender = sockaddr_in()
                var senderLen = socklen_t(MemoryLayout<sockaddr_in>.size)
                let n = withUnsafeMutablePointer(to: &sender) { ptr in
                    ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sa in
                        Darwin.recvfrom(fd, &recvBuf, recvBuf.count, 0, sa, &senderLen)
                    }
                }
                if n <= 0 {
                    if !found.isEmpty { break }
                    continue
                }
                let data = Data(recvBuf.prefix(n))
                if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   (json["service"] as? String == "pc-phone-remote") || (json["ok"] as? Bool == true)
                {
                    let host = (json["host"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? String(cString: inet_ntoa(sender.sin_addr))
                    let port = (json["port"] as? Int) ?? 8765
                    let name = (json["name"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? host
                    let mac = (json["mac"] as? String) ?? ""
                    let os = (json["os"] as? String) ?? "windows"
                    found["\(host):\(port)"] = DiscoveredPC(name: name, host: host, port: port, mac: mac, os: os)
                }
            }
        }
        return Array(found.values).sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    nonisolated private static func sendMagicPacket(macString: String, hostHint: String) {
        let hex = macString.filter { $0.isHexDigit }
        guard hex.count == 12 else { return }
        var macBytes: [UInt8] = []
        var idx = hex.startIndex
        for _ in 0..<6 {
            let next = hex.index(idx, offsetBy: 2)
            if let b = UInt8(hex[idx..<next], radix: 16) {
                macBytes.append(b)
            }
            idx = next
        }
        guard macBytes.count == 6 else { return }
        var packet = [UInt8](repeating: 0xFF, count: 6)
        for _ in 0..<16 { packet.append(contentsOf: macBytes) }

        let fd = Darwin.socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
        guard fd >= 0 else { return }
        defer { Darwin.close(fd) }
        var yes: Int32 = 1
        setsockopt(fd, SOL_SOCKET, SO_BROADCAST, &yes, socklen_t(MemoryLayout<Int32>.size))

        var targets = Set(["255.255.255.255"])
        for entry in localIPv4Interfaces() { targets.insert(entry.broadcast) }
        if !hostHint.isEmpty { targets.insert(hostHint) }

        for target in targets {
            for port in [UInt16(9), UInt16(7), UInt16(8765)] {
                var addr = sockaddr_in()
                addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
                addr.sin_family = sa_family_t(AF_INET)
                addr.sin_port = port.bigEndian
                if inet_pton(AF_INET, target, &addr.sin_addr) == 1 {
                    withUnsafePointer(to: &addr) { ptr in
                        ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sa in
                            _ = packet.withUnsafeBytes { buf in
                                Darwin.sendto(fd, buf.baseAddress, buf.count, 0, sa, socklen_t(MemoryLayout<sockaddr_in>.size))
                            }
                        }
                    }
                }
            }
        }
    }
}
