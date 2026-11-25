import SwiftUI
import UIKit
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
    @State private var showQrCameraSheet = false
    @State private var showEditorSheet = false
    @State private var editingProfile: DeviceProfile?
    @State private var showUnlockSheet = false
    @State private var showFileImporter = false
    @State private var showScreenSheet = false
    @State private var showAudioSheet = false

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                TopHeaderBar(
                    onOpenQrCamera: { showQrCameraSheet = true },
                    onOpenScanner: {
                        store.scanLAN()
                        showScannerSheet = true
                    }
                )

                TabView(selection: $store.currentTab) {
                    RemoteTabView(
                        onOpenUnlock: { showUnlockSheet = true },
                        onOpenAudio: {
                            Task { await store.refreshAudio() }
                            showAudioSheet = true
                        }
                    )
                    .tag(0)
                    .tabItem { Label("Remote", systemImage: "tv.and.mediabox") }

                    StudioProTabView(onOpenScreen: { showScreenSheet = true })
                        .tag(1)
                        .tabItem { Label("Studio Pro", systemImage: "slider.horizontal.3") }

                    TransferTabView(onPickFile: { showFileImporter = true })
                        .tag(2)
                        .tabItem { Label("Files", systemImage: "folder.badge.plus") }

                    SettingsTabView(
                        onOpenQrCamera: { showQrCameraSheet = true },
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
        .sheet(isPresented: $showQrCameraSheet) {
            QRScannerView { rawCode in
                if let url = URL(string: rawCode.trimmingCharacters(in: .whitespacesAndNewlines)) {
                    store.handleIncomingURL(url)
                }
            }
        }
        .sheet(isPresented: $showScreenSheet) {
            ScreenLiveSheet()
        }
        .sheet(isPresented: $showAudioSheet) {
            AudioMixerSheet()
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
                Task {
                    await store.refreshStatus()
                    await store.refreshBrightness()
                    await store.refreshCustomButtons()
                }
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
                Task {
                    await store.refreshStatus()
                    await store.refreshBrightness()
                    await store.refreshCustomButtons()
                }
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
    let onOpenQrCamera: () -> Void
    let onOpenScanner: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(store.activeProfile?.name ?? "PC Phone Remote Pro")
                        .font(.headline.bold())
                        .foregroundColor(.white)
                    Text(store.bannerMessage)
                        .font(.caption)
                        .foregroundColor(store.bannerIsError ? Theme.danger : Theme.success)
                }
                Spacer()
                Button(action: onOpenQrCamera) {
                    Image(systemName: "qrcode.viewfinder")
                        .foregroundColor(Theme.accent)
                        .padding(8)
                        .background(Theme.surface2)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                }
                Button(action: onOpenScanner) {
                    Image(systemName: "antenna.radiowaves.left.and.right")
                        .foregroundColor(Theme.accent)
                        .padding(8)
                        .background(Theme.surface2)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                }
                Button {
                    Task {
                        await store.refreshStatus()
                        await store.refreshBrightness()
                    }
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
    let onOpenAudio: () -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                CoachMarkBanner(
                    key: "remote",
                    message: "Tip: Use Unlock for Windows Face ID / PIN login, Audio Mixer for per-app volume, or Siri Shortcuts in the iOS Shortcuts app."
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
                        HStack {
                            Text("Media & Sound").font(.subheadline.bold()).foregroundColor(.gray)
                            Spacer()
                            Button(action: onOpenAudio) {
                                Label("Mixer & Outputs", systemImage: "slider.horizontal.below.rectangle")
                                    .font(.caption.bold())
                            }
                            .tint(Theme.accent)
                        }
                        HStack(spacing: 10) {
                            ActionBtn("Vol -", "speaker.wave.1") { store.performCommand(["action": "media", "key": "volume_down"]) }
                            ActionBtn("Mute", "speaker.slash") { store.performCommand(["action": "media", "key": "mute"]) }
                            ActionBtn("Vol +", "speaker.wave.3") { store.performCommand(["action": "media", "key": "volume_up"]) }
                        }
                        HStack(spacing: 10) {
                            ActionBtn("Prev", "backward.fill") { store.performCommand(["action": "media", "key": "previous"]) }
                            ActionBtn("Play/Pause", "playpause.fill") { store.performCommand(["action": "media", "key": "play_pause"]) }
                            ActionBtn("Next", "forward.fill") { store.performCommand(["action": "media", "key": "next"]) }
                        }
                    }
                    .padding()
                    .background(Theme.surface1)
                    .clipShape(RoundedRectangle(cornerRadius: 18))

                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Text("Display & Brightness").font(.subheadline.bold()).foregroundColor(.gray)
                            Spacer()
                            if store.brightnessSupported {
                                Text("\(Int(store.brightnessPercent))%").font(.caption.monospacedDigit()).foregroundColor(Theme.accent)
                            }
                        }
                        if store.brightnessSupported {
                            Slider(value: $store.brightnessPercent, in: 0...100, step: 5) { editing in
                                if !editing {
                                    store.performCommand(["action": "display.brightness", "brightness": Int(store.brightnessPercent)], successNote: "Brightness updated")
                                }
                            }
                            .tint(Theme.accent)
                        }
                        Button {
                            store.performCommand(["action": "display.off"], successNote: "Display turned off")
                        } label: {
                            Label("Turn Off Screen (Keep PC Awake)", systemImage: "display")
                                .font(.subheadline.bold())
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 10)
                        }
                        .buttonStyle(.bordered)
                        .tint(.white)
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
                    Text("Scan QR code or tap Auto-Find PC on Wi-Fi in the Devices tab.")
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
                Text(title).font(.caption.bold()).lineLimit(1)
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
    let onOpenScreen: () -> Void
    @State private var lastDrag: CGSize = .zero
    @State private var typedText: String = ""
    @State private var killConfirmPid: Int?
    @State private var killConfirmName: String = ""

    private let hotkeyList: [(String, String)] = [
        ("Alt+Tab", "alt_tab"),
        ("Win+D", "win_d"),
        ("Lang", "switch_lang"),
        ("Ctrl+C", "ctrl_c"),
        ("Ctrl+V", "ctrl_v"),
        ("Alt+F4", "alt_f4"),
        ("Task Mgr", "ctrl_shift_esc"),
        ("Enter", "enter"),
        ("Esc", "esc"),
    ]

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                CoachMarkBanner(
                    key: "studio",
                    message: "Tip: Open Live Screen View to tap directly on PC UI, type into focused windows, or run custom buttons."
                )

                Button(action: onOpenScreen) {
                    Label("Live PC Screen & Tap Control", systemImage: "macwindow.and.cursorarrow")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 13)
                }
                .buttonStyle(.borderedProminent)
                .tint(Theme.accent)

                VStack(alignment: .leading, spacing: 10) {
                    Text("Live Keyboard & Hotkeys").font(.subheadline.bold()).foregroundColor(.gray)
                    HStack {
                        TextField("Type straight into PC window...", text: $typedText)
                            .textFieldStyle(.roundedBorder)
                        Button("Send") {
                            let val = typedText
                            guard !val.isEmpty else { return }
                            typedText = ""
                            store.performCommand(["action": "keyboard.type", "text": val], successNote: "Typed on PC")
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(Theme.accent)
                    }
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(hotkeyList, id: \.1) { title, code in
                                Button(title) {
                                    store.performCommand(["action": "keyboard.hotkey", "hotkey": code])
                                }
                                .buttonStyle(.bordered)
                                .tint(.white)
                            }
                        }
                    }
                }
                .padding()
                .background(Theme.surface1)
                .clipShape(RoundedRectangle(cornerRadius: 18))

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
                        .frame(height: 165)
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
                        ActionBtn("Browser", "globe") { store.performCommand(["action": "deck.run", "macro": "browser"]) }
                        ActionBtn("Explorer", "folder") { store.performCommand(["action": "deck.run", "macro": "explorer"]) }
                        ActionBtn("Task Mgr", "cpu") { store.performCommand(["action": "deck.run", "macro": "task_manager"]) }
                        ActionBtn("Desktop", "macwindow") { store.performCommand(["action": "deck.run", "macro": "desktop"]) }
                        ActionBtn("Screenshot", "camera.viewfinder") { store.performCommand(["action": "deck.run", "macro": "screenshot"]) }
                        ActionBtn("Mute", "speaker.slash") { store.performCommand(["action": "deck.run", "macro": "mute"]) }
                    }
                    if !store.customButtons.isEmpty {
                        Text("Custom Buttons").font(.caption.bold()).foregroundColor(.gray).padding(.top, 6)
                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                            ForEach(Array(store.customButtons.enumerated()), id: \.offset) { _, btn in
                                Button {
                                    store.performCommand(["action": "deck.custom_run", "id": btn["id"] ?? ""])
                                } label: {
                                    Text("\(btn["icon"] ?? "⚡") \(btn["label"] ?? "Btn")")
                                        .font(.caption.bold())
                                        .foregroundColor(.white)
                                        .frame(maxWidth: .infinity)
                                        .padding(.vertical, 10)
                                        .background(Theme.surface2)
                                        .clipShape(RoundedRectangle(cornerRadius: 12))
                                }
                            }
                        }
                    }
                }
                .padding()
                .background(Theme.surface1)
                .clipShape(RoundedRectangle(cornerRadius: 18))

                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text("PC Processes").font(.subheadline.bold()).foregroundColor(.gray)
                        Spacer()
                        Button("Refresh") { Task { await store.refreshProcesses() } }
                    }
                    if store.processes.isEmpty {
                        Text("Tap Refresh to view top processes.").font(.caption).foregroundColor(.gray)
                    } else {
                        ForEach(Array(store.processes.enumerated()), id: \.offset) { _, proc in
                            let pid = (proc["pid"] as? NSNumber)?.intValue ?? 0
                            let name = (proc["name"] as? String) ?? "process"
                            let mb = (proc["mem_mb"] as? NSNumber)?.intValue ?? 0
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(name).font(.callout.bold()).foregroundColor(.white).lineLimit(1)
                                    Text("PID \(pid) • \(mb) MB").font(.caption2).foregroundColor(.gray)
                                }
                                Spacer()
                                Button {
                                    killConfirmPid = pid
                                    killConfirmName = name
                                } label: {
                                    Image(systemName: "xmark.circle.fill").foregroundColor(Theme.danger)
                                }
                            }
                            .padding(.vertical, 4)
                        }
                    }
                }
                .padding()
                .background(Theme.surface1)
                .clipShape(RoundedRectangle(cornerRadius: 18))
            }
            .padding()
        }
        .background(Theme.bg)
        .onAppear {
            Task {
                await store.refreshCustomButtons()
                await store.refreshProcesses()
            }
        }
        .alert("Terminate Process?", isPresented: Binding(get: { killConfirmPid != nil }, set: { if !$0 { killConfirmPid = nil } })) {
            Button("Terminate", role: .destructive) {
                if let pid = killConfirmPid {
                    store.performCommand(["action": "processes.kill", "pid": pid], successNote: "Terminated \(killConfirmName)")
                    Task { await store.refreshProcesses() }
                }
                killConfirmPid = nil
            }
            Button("Cancel", role: .cancel) { killConfirmPid = nil }
        } message: {
            Text("Terminate \(killConfirmName) (PID \(killConfirmPid ?? 0))?")
        }
    }
}

private struct ScreenLiveSheet: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) var dismiss
    @State private var screenImage: UIImage?
    @State private var monitors: [[String: Any]] = []
    @State private var selectedMonitor: Int = 0
    @State private var tapButton: String = "left"
    @State private var autoRefresh = false
    @State private var statusText = "Tap Refresh to capture PC screen"

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                if monitors.count > 1 {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack {
                            ForEach(Array(monitors.enumerated()), id: \.offset) { idx, mon in
                                Button((mon["name"] as? String) ?? "Monitor \(idx + 1)") {
                                    selectedMonitor = (mon["id"] as? NSNumber)?.intValue ?? idx
                                    Task { await capture() }
                                }
                                .buttonStyle(.borderedProminent)
                                .tint(selectedMonitor == idx ? Theme.accent : Theme.surface2)
                            }
                        }
                    }
                }

                GeometryReader { geo in
                    ZStack {
                        RoundedRectangle(cornerRadius: 14).fill(Theme.surface1)
                        if let img = screenImage {
                            Image(uiImage: img)
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                                .gesture(
                                    DragGesture(minimumDistance: 0)
                                        .onEnded { value in
                                            let nx = max(0.0, min(1.0, value.location.x / max(1.0, geo.size.width)))
                                            let ny = max(0.0, min(1.0, value.location.y / max(1.0, geo.size.height)))
                                            Task {
                                                guard let p = store.activeProfile else { return }
                                                _ = try? await store.callAction(profile: p, payload: [
                                                    "action": "screen.tap",
                                                    "nx": nx,
                                                    "ny": ny,
                                                    "monitor": selectedMonitor,
                                                    "button": tapButton,
                                                ])
                                                try? await Task.sleep(nanoseconds: 250_000_000)
                                                await capture()
                                            }
                                        }
                                )
                        } else {
                            Text(statusText).foregroundColor(.gray).padding()
                        }
                    }
                }

                Picker("Tap Mode", selection: $tapButton) {
                    Text("Left Click").tag("left")
                    Text("Right Click").tag("right")
                    Text("Double Click").tag("double")
                }
                .pickerStyle(.segmented)

                HStack {
                    Toggle("Auto Refresh", isOn: $autoRefresh)
                    Spacer()
                    Button("Capture") { Task { await capture() } }
                        .buttonStyle(.borderedProminent)
                        .tint(Theme.accent)
                }
            }
            .padding()
            .background(Theme.bg)
            .navigationTitle("Live Screen")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } }
            }
            .task { await capture() }
            .task(id: autoRefresh) {
                while autoRefresh {
                    try? await Task.sleep(nanoseconds: 700_000_000)
                    await capture()
                }
            }
        }
    }

    private func capture() async {
        guard let profile = store.activeProfile else { return }
        do {
            let res = try await store.callAction(profile: profile, payload: [
                "action": "screen.capture",
                "monitor": selectedMonitor,
                "max_width": 960,
                "quality": 60,
            ])
            if let b64 = res["image_b64"] as? String,
               let data = Data(base64Encoded: b64),
               let img = UIImage(data: data)
            {
                screenImage = img
                monitors = (res["monitors"] as? [[String: Any]]) ?? monitors
                statusText = ""
            }
        } catch {
            statusText = error.localizedDescription
        }
    }
}

private struct AudioMixerSheet: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section("Output Devices") {
                    if store.audioDevices.isEmpty {
                        Text("No audio outputs found").foregroundColor(.gray)
                    } else {
                        ForEach(Array(store.audioDevices.enumerated()), id: \.offset) { _, dev in
                            let devId = (dev["id"] as? String) ?? ""
                            let name = (dev["name"] as? String) ?? devId
                            let active = (dev["active"] as? Bool) ?? false
                            Button {
                                Task {
                                    guard let p = store.activeProfile else { return }
                                    _ = try? await store.callAction(profile: p, payload: ["action": "audio.set_output", "device_id": devId])
                                    await store.refreshAudio()
                                }
                            } label: {
                                HStack {
                                    Text(name)
                                    Spacer()
                                    if active { Image(systemName: "checkmark.circle.fill").foregroundColor(Theme.success) }
                                }
                            }
                        }
                    }
                }

                Section("App Volume Mixer") {
                    if store.audioSessions.isEmpty {
                        Text("No active audio apps").foregroundColor(.gray)
                    } else {
                        ForEach(Array(store.audioSessions.enumerated()), id: \.offset) { _, sess in
                            let pid = (sess["pid"] as? NSNumber)?.intValue ?? 0
                            let name = (sess["name"] as? String) ?? "App"
                            let vol = (sess["volume"] as? NSNumber)?.doubleValue ?? 100
                            let muted = (sess["muted"] as? Bool) ?? false
                            AppVolumeRow(pid: pid, name: name, initialVol: vol, initialMuted: muted)
                        }
                    }
                }
            }
            .navigationTitle("Audio Mixer")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } }
                ToolbarItem(placement: .primaryAction) { Button("Refresh") { Task { await store.refreshAudio() } } }
            }
        }
    }
}

private struct AppVolumeRow: View {
    @EnvironmentObject var store: AppStore
    let pid: Int
    let name: String
    @State private var vol: Double
    @State private var muted: Bool

    init(pid: Int, name: String, initialVol: Double, initialMuted: Bool) {
        self.pid = pid
        self.name = name
        _vol = State(initialValue: initialVol)
        _muted = State(initialValue: initialMuted)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(name).font(.subheadline.bold())
                Spacer()
                Button {
                    muted.toggle()
                    store.performCommand(["action": "audio.set_app_volume", "pid": pid, "muted": muted])
                } label: {
                    Image(systemName: muted ? "speaker.slash.fill" : "speaker.wave.2.fill")
                        .foregroundColor(muted ? Theme.danger : Theme.accent)
                }
                .buttonStyle(.borderless)
            }
            Slider(value: $vol, in: 0...100, step: 5) { editing in
                if !editing {
                    store.performCommand(["action": "audio.set_app_volume", "pid": pid, "volume": Int(vol)])
                }
            }
        }
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
                    message: "Tip: Upload files directly into PC Downloads/PCPhoneRemote or sync the real Windows/Linux Clipboard."
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
                    HStack {
                        Text("Live PC Clipboard").font(.subheadline.bold()).foregroundColor(.gray)
                        Spacer()
                        Button("Paste iPhone") {
                            store.clipboardText = UIPasteboard.general.string ?? store.clipboardText
                        }
                        .font(.caption)
                    }
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
                                    let val = (res["text"] as? String) ?? ""
                                    store.clipboardText = val
                                    UIPasteboard.general.string = val
                                }
                            }
                        }
                        .buttonStyle(.bordered)
                        Spacer()
                        Button("Push to PC") {
                            store.performCommand(["action": "clipboard.set", "text": store.clipboardText], successNote: "PC Clipboard updated")
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
    let onOpenQrCamera: () -> Void
    let onOpenScanner: () -> Void
    let onAddManual: () -> Void
    let onEdit: (DeviceProfile) -> Void

    var body: some View {
        List {
            Section("Quick Setup") {
                Button(action: onOpenQrCamera) {
                    Label("Scan QR Code on PC", systemImage: "qrcode.viewfinder")
                        .foregroundColor(Theme.accent)
                }
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
                        Text("Pair this iPhone on PC via the Desktop Control Center or scan an enrollment QR code.")
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
        ("📡", "1. One-Tap & QR Connection", "Scan the QR code from the PC Control Center or tap Auto-Find PC on Wi-Fi."),
        ("🖥", "2. Live Screen, Audio & Brightness", "View your PC screen, tap directly, adjust brightness, or switch audio output devices."),
        ("🎙️", "3. Siri Shortcuts & Live Keyboard", "Lock, sleep, or mute via Siri Shortcuts and type directly into any PC window."),
        ("🔐", "4. Files, Clipboard & Face ID", "Transfer files to PC Downloads, sync live Windows/Linux clipboard, and unlock with Face ID."),
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
