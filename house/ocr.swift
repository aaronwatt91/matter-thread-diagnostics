import Foundation
import Vision
import AppKit

func recognizeText(imagePath: String) {
    guard let image = NSImage(contentsOfFile: imagePath),
          let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        print("Failed to load \(imagePath)")
        return
    }
    let requestHandler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    let request = VNRecognizeTextRequest { (request, error) in
        guard let observations = request.results as? [VNRecognizedTextObservation] else { return }
        for observation in observations {
            guard let topCandidate = observation.topCandidates(1).first else { continue }
            let box = observation.boundingBox
            print(String(format: "Box: (%.3f, %.3f, %.3f, %.3f) Text: %@", box.origin.x, box.origin.y, box.size.width, box.size.height, topCandidate.string))
        }
    }
    request.recognitionLevel = .accurate
    try? requestHandler.perform([request])
}

let args = CommandLine.arguments
if args.count > 1 {
    recognizeText(imagePath: args[1])
}
