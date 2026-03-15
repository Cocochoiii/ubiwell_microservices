import CoreData
import SwiftUI

struct ContentView: View {
    @Environment(\.managedObjectContext) private var viewContext
    @EnvironmentObject var sensorPipeline: SensorPipelineService

    @FetchRequest(
        sortDescriptors: [NSSortDescriptor(keyPath: \SensorReading.timestamp, ascending: false)],
        animation: .default
    )
    private var readings: FetchedResults<SensorReading>

    var body: some View {
        NavigationView {
            VStack(alignment: .leading, spacing: 12) {
                Text("Daily reliability: \(sensorPipeline.dailyReliability, specifier: "%.3f")")
                Text("Processed: \(sensorPipeline.processedCount)")
                Text("Failed: \(sensorPipeline.failedCount)")
                HStack {
                    Button("Simulate Reading") {
                        sensorPipeline.ingest(value: Double.random(in: 45...145), context: viewContext)
                    }
                    Button("Upload Pending") {
                        sensorPipeline.uploadPendingReadings(context: viewContext)
                    }
                }
                List(readings.prefix(20), id: \.id) { reading in
                    VStack(alignment: .leading) {
                        Text(reading.sensorType ?? "unknown").font(.headline)
                        Text("value: \(reading.value, specifier: "%.2f")")
                        Text("label: \(reading.inferenceLabel ?? "n/a")")
                        Text("uploaded: \(reading.isUploaded ? "yes" : "no")")
                    }
                }
            }
            .padding()
            .navigationTitle("UbiWell Edge")
        }
    }
}
