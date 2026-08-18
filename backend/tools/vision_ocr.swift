import AppKit
import Foundation
import ImageIO
import Vision

guard CommandLine.arguments.count == 3 else {
    fputs("Usage: vision_ocr <frames-directory> <timestamps-json>\n", stderr)
    exit(64)
}

let framesDirectory = URL(fileURLWithPath: CommandLine.arguments[1])
let timestampURL = URL(fileURLWithPath: CommandLine.arguments[2])
let timestamps = (try? JSONSerialization.jsonObject(with: Data(contentsOf: timestampURL))) as? [Double] ?? []

func timestamp(_ seconds: Double) -> String {
    let hours = Int(seconds) / 3600
    let minutes = (Int(seconds) % 3600) / 60
    return String(format: "%02d:%02d:%05.2f", hours, minutes, seconds.truncatingRemainder(dividingBy: 60))
}

func recognize(_ imageURL: URL) throws -> String {
    guard let source = CGImageSourceCreateWithURL(imageURL as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { return "" }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.automaticallyDetectsLanguage = true
    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    try handler.perform([request])
    return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        .joined(separator: " ")
        .trimmingCharacters(in: .whitespacesAndNewlines)
}

let files = try FileManager.default.contentsOfDirectory(at: framesDirectory, includingPropertiesForKeys: nil)
    .filter { $0.pathExtension.lowercased() == "jpg" }
    .sorted { $0.lastPathComponent < $1.lastPathComponent }

var rows: [[String: String]] = []
for (offset, frame) in files.enumerated() {
    let text = try recognize(frame)
    guard !text.isEmpty else { continue }
    let startSeconds = offset < timestamps.count ? timestamps[offset] : Double(offset)
    let endSeconds = offset + 1 < timestamps.count ? timestamps[offset + 1] : startSeconds
    rows.append(["start": timestamp(startSeconds), "end": timestamp(endSeconds), "text": text])
}

let data = try JSONSerialization.data(withJSONObject: rows, options: [])
print(String(decoding: data, as: UTF8.self))
