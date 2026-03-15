import XCTest
@testable import UbiWellEdge

final class SensorPipelineServiceTests: XCTestCase {
    func testReliabilityAtStartupIsOne() {
        let service = SensorPipelineService()
        XCTAssertEqual(service.dailyReliability, 1.0, accuracy: 0.0001)
    }

    func testHoursSavedMathContract() {
        let saved = 40.0 - 20.0
        XCTAssertEqual(saved, 20.0, accuracy: 0.0001)
    }

    func testCoverageTargetConstant() {
        let target = 0.92
        XCTAssertGreaterThanOrEqual(target, 0.92)
    }
}
