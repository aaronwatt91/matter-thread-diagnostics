import Foundation
import Vision
import AppKit

func run(path: String) {
    guard let image = NSImage(contentsOfFile: path),
          let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        return
    }
    let requestHandler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    let request = VNRecognizeTextRequest { (request, error) in
        guard let observations = request.results as? [VNRecognizedTextObservation] else { return }
        for observation in observations {
            guard let top = observation.topCandidates(1).first else { continue }
            let b = observation.boundingBox
            print(String(format: "y:%.2f x:%.2f w:%.2f h:%.2f | %@", 1.0 - b.origin.y - b.size.height, b.origin.x, b.size.width, b.size.height, top.string))
        }
    }
    request.recognitionLevel = .accurate
    try? requestHandler.perform([request])
}

let args = CommandLine.arguments
if args.count > 1 {
    run(path: args[1])
}
