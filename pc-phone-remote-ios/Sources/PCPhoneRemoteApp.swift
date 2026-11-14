import SwiftUI

@main
struct PCPhoneRemoteApp: App {
    @StateObject private var store = AppStore()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(store)
                .preferredColorScheme(.dark)
                .onOpenURL { url in
                    store.handleIncomingURL(url)
                }
        }
    }
}
