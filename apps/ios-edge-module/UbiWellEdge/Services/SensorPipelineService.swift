import CoreData
import Foundation

final class SensorPipelineService: ObservableObject {
    @Published private(set) var processedCount: Int = 0
    @Published private(set) var failedCount: Int = 0
    @Published private(set) var dailyReliability: Double = 1.0

    private let inferenceEngine = EdgeInferenceEngine()

    func ingest(value: Double, context: NSManagedObjectContext) {
        context.performAndWait {
            let reading = SensorReading(context: context)
            reading.id = UUID()
            reading.timestamp = Date()
            reading.sensorType = "heart_rate"
            reading.value = value
            let prediction = inferenceEngine.infer(value: value)
            reading.inferenceLabel = prediction.label
            reading.inferenceConfidence = prediction.confidence
            reading.isUploaded = false

            do {
                try context.save()
                processedCount += 1
            } catch {
                failedCount += 1
            }
            dailyReliability = computeReliability()
        }
    }

    func uploadPendingReadings(context: NSManagedObjectContext) {
        let request: NSFetchRequest<SensorReading> = SensorReading.fetchRequest()
        request.predicate = NSPredicate(format: "isUploaded == NO")
        request.fetchLimit = 1000
        context.performAndWait {
            do {
                let items = try context.fetch(request)
                for item in items {
                    item.isUploaded = true
                }
                try context.save()
            } catch {
                failedCount += 1
                dailyReliability = computeReliability()
            }
        }
    }

    private func computeReliability() -> Double {
        let total = processedCount + failedCount
        guard total > 0 else { return 1.0 }
        return Double(processedCount) / Double(total)
    }
}
