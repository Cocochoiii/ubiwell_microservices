import SwiftUI

@main
struct UbiWellEdgeApp: App {
    let persistenceController = PersistenceController.shared
    @StateObject private var sensorPipeline = SensorPipelineService()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(\.managedObjectContext, persistenceController.container.viewContext)
                .environmentObject(sensorPipeline)
        }
    }
}
