import CoreData
import Foundation

extension SensorReading {
    @nonobjc public class func fetchRequest() -> NSFetchRequest<SensorReading> {
        NSFetchRequest<SensorReading>(entityName: "SensorReading")
    }

    @NSManaged public var id: UUID?
    @NSManaged public var timestamp: Date?
    @NSManaged public var sensorType: String?
    @NSManaged public var value: Double
    @NSManaged public var inferenceLabel: String?
    @NSManaged public var inferenceConfidence: Double
    @NSManaged public var isUploaded: Bool
}
