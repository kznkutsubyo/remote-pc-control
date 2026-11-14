import SwiftUI
import UniformTypeIdentifiers

private enum Theme {
    static let bg = Color(red: 0.043, green: 0.043, blue: 0.063)       // #0B0B10
    static let surface1 = Color(red: 0.075, green: 0.078, blue: 0.11)  // #13141C
    static let surface2 = Color(red: 0.114, green: 0.122, blue: 0.173) // #1D1F2C
    static let accent = Color(red: 0.545, green: 0.486, blue: 1.0)     // #8B7CFF
    static let success = Color(red: 0.239, green: 0.839, blue: 0.549)  // #3DD68C
    static let warning = Color(red: 0.96, green: 0.62, blue: 0.043)    // #F59E0B
    static let danger = Color(red: 0.937, green: 0.267, blue: 0.267)   // #EF4444
}

struct ContentView: View {
    @EnvironmentObject var store: AppStore
    @State private var showScannerSheet = false
    @State private var showEditorSheet = false
    @State private var editingProfile: DeviceProfile?
    @State private var showUnlockSheet = false
    @State private var showFileImporter = false

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                TopHeaderBar(onOpenScanner: {
                    store.scanLAN()
                    showScannerSheet = true
                })

                TabView(selection: $store.currentTab) {
                    RemoteTabView(onOpenUnlock: { showUnlockSheet = true })
                        .tag(0)
                        .tabItem { Label("Remote", systemImage: "tv.and.mediabox") }

                    StudioProTabView()
                        .tag(1)
                        .tabItem { Label("Studio Pro", systemImage: "slider.horizontal.3") }

                    TransferTabView(onPickFile: { showFileImporter = true })
                        .tag(2)
                        .tabItem { Label("Files", systemImage: "folder.badge.plus") }

                    SettingsTabView(
                        onOpenScanner: {
                            store.scanLAN()
                            showScannerSheet = true
                        },
                        onAddManual: {
                            editingProfile = nil
                            showEditorSheet = true
                        },
                        onEdit: { profile in
                            editingProfile = profile
                            showEditorSheet = true
                        }
                    )
                    .tag(3)
                    .tabItem { Label("Devices", systemImage: "desktopcomputer") }
                }
                .tint(Theme.accent)
            }
        }
        .sheet(isPresented: $store.showOnboardingTour) {
            OnboardingTourSheet { store.completeTour() }
        }
        .sheet(isPresented: $showScannerSheet) {
            LanScannerSheet(onSelect: { pc in
                editingProfile = DeviceProfile(
                    name: pc.name,
                    host: pc.host,
                    port: String(pc.port),
                    pin: "",
                    mac: pc.mac
                )
                showScannerSheet = false
                showEditorSheet = true
            })
        }
        .sheet(isPresented: $showEditorSheet) {
            DeviceEditorSheet(initial: editingProfile) { saved in
                store.addOrUpdateProfile(saved)
                store.currentTab = 0
                Task { await store.refreshStatus() }
            }
        }
        .sheet(isPresented: $showUnlockSheet) {
            UnlockSheetView()
        }
        .sheet(item: Binding(
            get: { store.pendingEnrollUri.map { EnrollWrapper(parsed: $0) } },
            set: { if $0 == nil { store.pendingEnrollUri = nil } }
        )) { wrapper in
            EnrollSheetView(parsed: wrapper.parsed)
        }
        .fileImporter(isPresented: $showFileImporter, allowedContentTypes: [.item]) { result in
            if case .success(let url) = result {
                store.uploadFile(url: url)
            }
        }
        .onAppear {
            if store.activeProfile != nil {
                Task { await store.refreshStatus() }
            }
        }
    }
}

private struct EnrollWrapper: Identifiable {
    let id = UUID()
    let parsed: ParsedEnrollUri
}

private struct TopHeaderBar: View {
    @EnvironmentObject var store: AppStore
    let onOpenScanner: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(store.activeProfile?.name ?? "PC Phone Remote Pro")
                        .font(.headline.bold())
                        .foregroundColor(.white)
                    Text(store.bannerMessage)
                        .font(.caption)
                        .foregroundColor(store.bannerIsError ? Theme.danger : Theme.success)
                }
                Spacer()
                Button(action: onOpenScanner) {
                    Image(systemName: "antenna.radiowaves.left.and.right")
                        .foregroundColor(Theme.accent)
                        .padding(8)
                        .background(Theme.surface2)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                }
                Button {
                    Task { await store.refreshStatus() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .foregroundColor(.white)
                        .padding(8)
                        .background(Theme.surface2)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                }
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
        .background(Theme.surface1)
    }
}

private struct CoachMarkBanner: View {
    @EnvironmentObject var store: AppStore
    let key: String
    let message: String

    var body: some View {
        if !store.dismissedTips.contains(key) {
            HStack(alignment: .center, spacing: 10) {
                Text("💡")
                Text(message)
                    .font(.caption)
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Button("✕") {
                    withAnimation { store.dismissTip(key) }
                }
                .foregroundColor(.gray)
            }
            .padding(12)
            .background(Theme.accent.opacity(0.14))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.accent.opacity(0.45), lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 14))
        }
    }
}

private struct RemoteTabView: View {
    @EnvironmentObject var store: AppStore
    let onOpenUnlock: () -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                CoachMarkBanner(
                    key: "remote",
                    message: "Tip: Use Unlock for Windows Face ID / PIN login or 1-tap Linux session unlock, and Wake PC to boot over LAN."
                )

                if let profile = store.activeProfile {
                    let cpu = (store.statusData["cpu"] as? NSNumber)?.intValue
                    let ram = (store.statusData["ram"] as? NSNumber)?.intValue
                    let disk = (store.statusData["disk"] as? NSNumber)?.intValue
                    let osName = (store.statusData["os"] as? String) ?? "pc"

                    HStack(spacing: 10) {
                        TelemetryCard(title: "CPU", value: cpu.map { "\($0)%" } ?? "--")
                        TelemetryCard(title: "RAM", value: ram.map { "\($0)%" } ?? "--")
                        TelemetryCard(title: "Disk", value: disk.map { "\($0)%" } ?? "--")
                        TelemetryCard(title: "OS", value: osName.capitalized)
                    }

                    Button(action: onOpenUnlock) {
                        Label("Sign In / Unlock PC", systemImage: "lock.open.fill")
                            .font(.headline)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(Theme.accent)

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Media & Volume").font(.subheadline.bold()).foregroundColor(.gray)
                        HStack(spacing: 10) {
                            ActionBtn("Vol -", "speaker.wave.1") { store.performCommand(["action": "media", "op": "vol_down"]) }
                            ActionBtn("Mute", "speaker.slash") { store.performCommand(["action": "media", "op": "mute"]) }
                            ActionBtn("Vol +", "speaker.wave.3") { store.performCommand(["action": "media", "op": "vol_up"]) }
                        }
                        HStack(spacing: 10) {
                            ActionBtn("Prev", "backward.fill") { store.performCommand(["action": "media", "op": "prev"]) }
                            ActionBtn("Play/Pause", "playpause.fill") { store.performCommand(["action": "media", "op": "play_pause"]) }
                            ActionBtn("Next", "forward.fill") { store.performCommand(["action": "media", "op": "next"]) }
                        }
                    }
                    .padding()
                    .background(Theme.surface1)
                    .clipShape(RoundedRectangle(cornerRadius: 18))

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Power & Session").font(.subheadline.bold()).foregroundColor(.gray)
                        HStack(spacing: 10) {
                            ActionBtn("Wake PC", "bolt.fill") { store.wakePc(profile) }
                            ActionBtn("Lock", "lock.fill") { store.performCommand(["action": "command", "command": "lock"]) }
                            ActionBtn("Sleep", "moon.fill") { store.performCommand(["action": "command", "command": "sleep"]) }
                        }
                    }
                    .padding()
                    .background(Theme.surface1)
                    .clipShape(RoundedRectangle(cornerRadius: 18))
                } else {
                    Text("Add or auto-find your Windows / Linux PC in the Devices tab.")
                        .foregroundColor(.gray)
                        .padding(.top, 40)
                }
            }
            .padding()
        }
        .background(Theme.bg)
    }
}

private struct TelemetryCard: View {
    let title: String
    let value: String

    var body: some View {
        VStack(spacing: 4) {
            Text(value).font(.headline.bold()).foregroundColor(.white)
            Text(title).font(.caption2).foregroundColor(.gray)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(Theme.surface1)
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}

private struct ActionBtn: View {
    let title: String
    let icon: String
    let action: () -> Void

    init(_ title: String, _ icon: String, action: @escaping () -> Void) {
        self.title = title
        self.icon = icon
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            VStack(spacing: 6) {
                Image(systemName: icon).font(.title3)
                Text(title).font(.caption.bold())
            }
            .foregroundColor(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .background(Theme.surface2)
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
    }
}

private struct StudioProTabView: View {
    @EnvironmentObject var store: AppStore
    @State private var lastDrag: CGSize = .zero

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                CoachMarkBanner(
                    key: "studio",
                    message: "Tip: Drag on the Touchpad surface to move your Windows/Linux cursor, or tap macros below."
                )

                VStack(alignment: .leading, spacing: 8) {
                    Text("Wireless Touchpad").font(.subheadline.bold()).foregroundColor(.gray)
                    RoundedRectangle(cornerRadius: 18)
                        .fill(Theme.surface2)
                        .overlay(
                            VStack {
                                Image(systemName: "hand.draw.fill").font(.largeTitle).foregroundColor(Theme.accent)
                                Text("Drag to move cursor • Tap to click").font(.caption).foregroundColor(.gray)
                            }
                        )
                        .frame(height: 180)
                        .gesture(
                            DragGesture()
                                .onChanged { value in
                                    let dx = Int(value.translation.width - lastDrag.width)
                                    let dy = Int(value.translation.height - lastDrag.height)
                                    lastDrag = value.translation
                                    if abs(dx) > 1 || abs(dy) > 1 {
                                        store.sendTouchpad(op: "move", dx: dx * 2, dy: dy * 2)
                                    }
                                }
                                .onEnded { _ in lastDrag = .zero }
                        )
                        .onTapGesture {
                            store.sendTouchpad(op: "click", button: "left")
                        }

                    HStack(spacing: 10) {
                        ActionBtn("Left Click", "cursorarrow.click") { store.sendTouchpad(op: "click", button: "left") }
                        ActionBtn("Right Click", "cursorarrow.click.2") { store.sendTouchpad(op: "click", button: "right") }
                    }
                }
                .padding()
                .background(Theme.surface1)
                .clipShape(RoundedRectangle(cornerRadius: 18))

                VStack(alignment: .leading, spacing: 10) {
                    Text("Stream Deck Macros").font(.subheadline.bold()).foregroundColor(.gray)
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                        ActionBtn("Browser", "globe") { store.performCommand(["action": "deck", "macro": "browser"]) }
                        ActionBtn("Terminal", "terminal") { store.performCommand(["action": "deck", "macro": "terminal"]) }
                        ActionBtn("Task Mgr", "cpu") { store.performCommand(["action": "deck", "macro": "taskmgr"]) }
                        ActionBtn("Downloads", "folder") { store.performCommand(["action": "deck", "macro": "downloads"]) }
                        ActionBtn("Min All", "rectangle.compress.vertical") { store.performCommand(["action": "deck", "macro": "minimize_all"]) }
                        ActionBtn("Screenshot", "camera.viewfinder") { store.performCommand(["action": "deck", "macro": "screenshot"]) }
                    }
                }
                .padding()
                .background(Theme.surface1)
                .clipShape(RoundedRectangle(cornerRadius: 18))
            }
            .padding()
        }
        .background(Theme.bg)
    }
}

private struct TransferTabView: View {
    @EnvironmentObject var store: AppStore
    let onPickFile: () -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                CoachMarkBanner(
                    key: "transfer",
                    message: "Tip: Upload files directly into your PC Downloads/PCPhoneRemote folder or push text to PC Clipboard."
                )

                Button(action: onPickFile) {
                    Label("Send File from iPhone to PC", systemImage: "square.and.arrow.up.fill")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                }
                .buttonStyle(.borderedProminent)
                .tint(Theme.accent)

                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text("PC Shared Files").font(.subheadline.bold()).foregroundColor(.gray)
                        Spacer()
                        Button("Refresh") { Task { await store.refreshFiles() } }
                    }
                    if store.sharedFiles.isEmpty {
                        Text("Tap Refresh to list files from PC.").font(.caption).foregroundColor(.gray)
                    } else {
                        ForEach(store.sharedFiles) { file in
                            HStack {
                                Image(systemName: "doc.fill").foregroundColor(Theme.accent)
                                Text(file.name).foregroundColor(.white).lineLimit(1)
                                Spacer()
                                Text(ByteCountFormatter.string(fromByteCount: file.size, countStyle: .file))
                                    .font(.caption).foregroundColor(.gray)
                            }
                            .padding(.vertical, 6)
                        }
                    }
                }
                .padding()
                .background(Theme.surface1)
                .clipShape(RoundedRectangle(cornerRadius: 18))

                VStack(alignment: .leading, spacing: 8) {
                    Text("Live Clipboard").font(.subheadline.bold()).foregroundColor(.gray)
                    TextEditor(text: $store.clipboardText)
                        .frame(minHeight: 90)
                        .scrollContentBackground(.hidden)
                        .padding(8)
                        .background(Theme.surface2)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                    HStack {
                        Button("Pull from PC") {
                            Task {
                                guard let p = store.activeProfile else { return }
                                if let res = try? await store.callAction(profile: p, payload: ["action": "clipboard.get"]) {
                                    store.clipboardText = (res["text"] as? String) ?? ""
                                }
                            }
                        }
                        .buttonStyle(.bordered)
                        Spacer()
                        Button("Push to PC") {
                            store.performCommand(["action": "clipboard.set", "text": store.clipboardText], successNote: "Clipboard synced")
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(Theme.accent)
                    }
                }
                .padding()
                .background(Theme.surface1)
                .clipShape(RoundedRectangle(cornerRadius: 18))
            }
            .padding()
        }
        .background(Theme.bg)
        .onAppear { Task { await store.refreshFiles() } }
    }
}

private struct SettingsTabView: View {
    @EnvironmentObject var store: AppStore
    let onOpenScanner: () -> Void
    let onAddManual: () -> Void
    let onEdit: (DeviceProfile) -> Void

    var body: some View {
        List {
            Section("Quick Setup") {
                Button(action: onOpenScanner) {
                    Label("Auto-Find PC on Wi-Fi (UDP 8766)", systemImage: "antenna.radiowaves.left.and.right")
                        .foregroundColor(Theme.accent)
                }
                Button(action: onAddManual) {
                    Label("Add PC Manually", systemImage: "plus.circle.fill")
                }
                Button {
                    store.replayTour()
                } label: {
                    Label("Show Quick Start Tour & Hints", systemImage: "lightbulb.fill")
                        .foregroundColor(Theme.warning)
                }
            }

            Section("Saved PCs") {
                ForEach(Array(store.profiles.enumerated()), id: \.element.id) { idx, profile in
                    HStack {
                        VStack(alignment: .leading) {
                            Text(profile.name).bold()
                            Text("\(profile.host):\(profile.port)").font(.caption).foregroundColor(.gray)
                        }
                        Spacer()
                        if idx == store.selectedIndex {
                            Image(systemName: "checkmark.circle.fill").foregroundColor(Theme.success)
                        }
                        Button { onEdit(profile) } label: {
                            Image(systemName: "pencil").padding(.leading, 8)
                        }
                        .buttonStyle(.borderless)
                    }
                    .contentShape(Rectangle())
                    .onTapGesture {
                        store.selectedIndex = idx
                        store.persistProfiles()
                        Task { await store.refreshStatus() }
                    }
                }
                .onDelete { offsets in
                    offsets.forEach { store.deleteProfile(id: store.profiles[$0].id) }
                }
            }
        }
        .scrollContentBackground(.hidden)
        .background(Theme.bg)
    }
}

private struct LanScannerSheet: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) var dismiss
    let onSelect: (DiscoveredPC) -> Void

    var body: some View {
        NavigationStack {
            List {
                if store.isScanning {
                    HStack(spacing: 12) {
                        ProgressView()
                        Text("Scanning local Wi-Fi network (port 8766)...")
                    }
                } else if store.discoveredPCs.isEmpty {
                    Text("No PC responded. Ensure PC Phone Remote Pro is running on the same Wi-Fi network.")
                        .foregroundColor(.gray)
                } else {
                    ForEach(store.discoveredPCs) { pc in
                        Button { onSelect(pc) } label: {
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(pc.name).font(.headline)
                                    Text("\(pc.host):\(pc.port) • \(pc.os.uppercased())").font(.caption).foregroundColor(.gray)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                            }
                        }
                    }
                }
            }
            .navigationTitle("Select PC on Wi-Fi")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } }
                ToolbarItem(placement: .primaryAction) { Button("Rescan") { store.scanLAN() } }
            }
        }
    }
}

private struct DeviceEditorSheet: View {
    @Environment(\.dismiss) var dismiss
    @State private var name: String
    @State private var host: String
    @State private var port: String
    @State private var pin: String
    let existingId: String?
    let mac: String
    let onSave: (DeviceProfile) -> Void

    init(initial: DeviceProfile?, onSave: @escaping (DeviceProfile) -> Void) {
        self.existingId = initial?.id
        self.mac = initial?.mac ?? ""
        _name = State(initialValue: initial?.name ?? "")
        _host = State(initialValue: initial?.host ?? "")
        _port = State(initialValue: initial?.port ?? "8765")
        _pin = State(initialValue: initial?.pin ?? "")
        self.onSave = onSave
    }

    var body: some View {
        NavigationStack {
            Form {
                TextField("PC Name", text: $name)
                TextField("IP / Host", text: $host).autocorrectionDisabled()
                TextField("Port (8765)", text: $port).keyboardType(.numberPad)
                SecureField("Unified PIN", text: $pin)
            }
            .navigationTitle(existingId == nil ? "Add PC" : "Edit PC")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        onSave(DeviceProfile(
                            id: existingId ?? UUID().uuidString,
                            name: name.isEmpty ? host : name,
                            host: host.trimmingCharacters(in: .whitespaces),
                            port: port.isEmpty ? "8765" : port,
                            pin: pin,
                            mac: mac
                        ))
                        dismiss()
                    }
                    .disabled(host.isEmpty || pin.isEmpty)
                }
            }
        }
    }
}

private struct UnlockSheetView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) var dismiss
    @State private var password = ""
    @State private var phonePin = ""
    @State private var message = ""
    @State private var isError = false
    @State private var busy = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                if let profile = store.activeProfile {
                    let unlockSnap = store.statusData["unlock"] as? [String: Any]
                    let isLinux = (unlockSnap?["vault_mode"] as? String) == "linux_logind"
                    let meta = UnlockCrypto.loadMeta(profileId: profile.id)

                    if isLinux {
                        Button("Unlock Linux Session") {
                            busy = true
                            Task {
                                do {
                                    let res = try await store.callAction(profile: profile, payload: ["action": "unlock.linux"])
                                    message = (res["message"] as? String) ?? "Unlocked"
                                    isError = false
                                } catch {
                                    message = error.localizedDescription
                                    isError = true
                                }
                                busy = false
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(Theme.accent)
                        .disabled(busy)
                    } else if let meta {
                        if meta.requiresPhonePin {
                            SecureField("Phone Unlock PIN", text: $phonePin)
                                .textFieldStyle(.roundedBorder)
                        } else {
                            SecureField("Optional Windows Password (blank = Face ID vault)", text: $password)
                                .textFieldStyle(.roundedBorder)
                        }
                        Button(meta.requiresPhonePin ? "Unlock with PIN" : "Unlock with Face ID") {
                            Task { await performWindowsUnlock(profile: profile, meta: meta) }
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(Theme.accent)
                        .disabled(busy)
                    } else {
                        Text("Pair this iPhone on PC via configure.py or enter a pcphone://enroll link.")
                            .multilineTextAlignment(.center)
                            .foregroundColor(.gray)
                    }

                    if !message.isEmpty {
                        Text(message)
                            .foregroundColor(isError ? Theme.danger : Theme.success)
                            .font(.callout.bold())
                    }
                }
                Spacer()
            }
            .padding()
            .navigationTitle("Sign In / Unlock")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } }
            }
        }
    }

    private func performWindowsUnlock(profile: DeviceProfile, meta: EnrollmentMeta) async {
        busy = true
        defer { busy = false }
        if !meta.requiresPhonePin && password.isEmpty {
            let auth = await UnlockCrypto.authenticateBiometrics(reason: "Sign in to \(profile.name)")
            if case .failure(let err) = auth {
                message = err.localizedDescription
                isError = true
                return
            }
        }
        do {
            let challenge = try await store.callAction(profile: profile, payload: ["action": "unlock.challenge"])
            let submit = try UnlockCrypto.buildUnlockSubmitRequest(
                profileId: profile.id,
                challenge: challenge,
                password: password.isEmpty ? nil : password,
                phonePin: phonePin.isEmpty ? nil : phonePin
            )
            let res = try await store.callAction(profile: profile, payload: submit)
            message = (res["message"] as? String) ?? "Unlocked"
            isError = false
        } catch {
            message = error.localizedDescription
            isError = true
        }
    }
}

private struct EnrollSheetView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) var dismiss
    let parsed: ParsedEnrollUri
    @State private var status = "Confirm binding for Face ID / PIN sign-in."
    @State private var busy = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                Text(parsed.pcName).font(.title2.bold())
                Text(parsed.qualifiedUser).foregroundColor(.gray)
                Text(status).multilineTextAlignment(.center)
                Button("Pair Device") {
                    guard let profile = store.activeProfile else { return }
                    busy = true
                    Task {
                        do {
                            let prepared = try UnlockCrypto.prepareEnrollment(profileId: profile.id, parsed: parsed)
                            _ = try await store.callAction(profile: profile, payload: prepared.request)
                            _ = prepared.commit()
                            dismiss()
                        } catch {
                            status = error.localizedDescription
                        }
                        busy = false
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(Theme.accent)
                .disabled(busy)
            }
            .padding()
            .navigationTitle("Pair Phone Unlock")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
            }
        }
    }
}

private struct OnboardingTourSheet: View {
    let onFinish: () -> Void
    @State private var page = 0

    private let steps: [(icon: String, title: String, body: String)] = [
        ("📡", "1. One-Tap PC Connection", "Run the installer on Windows or Linux, then tap Auto-Find PC on Wi-Fi or scan the QR code."),
        ("🔐", "2. Unified Security PIN", "One PIN connects your iPhone and unlocks the Windows or Linux sign-in screen."),
        ("🖱️", "3. Trackpad, Media & WoL", "Control cursor movement, media playback, power, sleep, and Wake-on-LAN effortlessly."),
        ("📂", "4. Linux, Files & Face ID", "Send files straight to PC Downloads, sync clipboard text, and unlock Windows with Face ID."),
    ]

    var body: some View {
        VStack(spacing: 20) {
            Spacer()
            Text(steps[page].icon).font(.system(size: 56))
            Text(steps[page].title).font(.title2.bold()).multilineTextAlignment(.center)
            Text(steps[page].body).foregroundColor(.gray).multilineTextAlignment(.center).padding(.horizontal)
            Spacer()
            HStack {
                if page > 0 {
                    Button("Back") { page -= 1 }
                } else {
                    Button("Skip") { onFinish() }.foregroundColor(.gray)
                }
                Spacer()
                Button(page < steps.count - 1 ? "Next" : "Get Started") {
                    if page < steps.count - 1 { page += 1 } else { onFinish() }
                }
                .buttonStyle(.borderedProminent)
                .tint(Theme.accent)
            }
            .padding()
        }
        .padding()
        .background(Theme.bg)
    }
}
