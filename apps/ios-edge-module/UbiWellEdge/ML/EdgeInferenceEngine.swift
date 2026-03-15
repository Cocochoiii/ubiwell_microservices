import Foundation
import TensorFlowLite

final class EdgeInferenceEngine {
    private var interpreter: Interpreter?
    private let labels = ["normal", "warning", "critical"]

    init() {
        guard let modelPath = Bundle.main.path(forResource: "sensor_classifier", ofType: "tflite") else {
            return
        }
        do {
            var options = Interpreter.Options()
            options.threadCount = 2
            let interpreter = try Interpreter(modelPath: modelPath, options: options)
            try interpreter.allocateTensors()
            self.interpreter = interpreter
        } catch {
            self.interpreter = nil
        }
    }

    func infer(value: Double) -> InferenceResult {
        guard let interpreter else {
            return fallback(value: value)
        }
        do {
            var input = Float32(value)
            let inputData = Data(bytes: &input, count: MemoryLayout<Float32>.size)
            try interpreter.copy(inputData, toInputAt: 0)
            try interpreter.invoke()
            let output = try interpreter.output(at: 0)
            let confidence = output.data.withUnsafeBytes { ptr -> Float32 in
                guard let base = ptr.bindMemory(to: Float32.self).baseAddress else { return 0.0 }
                return base.pointee
            }
            let clamped = max(0.0, min(1.0, Double(confidence)))
            let label = clamped > 0.8 ? labels[2] : (clamped > 0.5 ? labels[1] : labels[0])
            return InferenceResult(label: label, confidence: clamped)
        } catch {
            return fallback(value: value)
        }
    }

    private func fallback(value: Double) -> InferenceResult {
        if value > 120 {
            return InferenceResult(label: "critical", confidence: 0.91)
        }
        if value > 95 {
            return InferenceResult(label: "warning", confidence: 0.72)
        }
        return InferenceResult(label: "normal", confidence: 0.88)
    }
}
