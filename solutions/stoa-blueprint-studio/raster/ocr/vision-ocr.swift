// Local Apple Vision OCR for raster drawings (macOS only, no network, no model cost).
// Reads text at 0°, 90° and 270° so vertical door/window tags are found, maps every box
// back to the original image and prints JSON: [{"text","conf","box":[x0,y0,x1,y1],"rot"}]
// with normalized top-left-origin coordinates. Usage: vision-ocr <image>
import AppKit
import Foundation
import Vision

func rotated(_ img: CGImage, clockwise90 times: Int) -> CGImage? {
  if times % 4 == 0 { return img }
  let w = img.width, h = img.height
  let (nw, nh) = times % 2 == 1 ? (h, w) : (w, h)
  guard let ctx = CGContext(data: nil, width: nw, height: nh, bitsPerComponent: 8, bytesPerRow: 0,
                            space: CGColorSpaceCreateDeviceRGB(),
                            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
  ctx.setFillColor(CGColor(gray: 1, alpha: 1)); ctx.fill(CGRect(x: 0, y: 0, width: nw, height: nh))
  ctx.translateBy(x: CGFloat(nw) / 2, y: CGFloat(nh) / 2)
  ctx.rotate(by: -CGFloat(times) * .pi / 2)  // CoreGraphics is y-up: negative angle = clockwise on screen
  ctx.draw(img, in: CGRect(x: -CGFloat(w) / 2, y: -CGFloat(h) / 2, width: CGFloat(w), height: CGFloat(h)))
  return ctx.makeImage()
}

// Map a point (top-left normalized) in the rotated image back to the original image.
func unrotate(_ x: Double, _ y: Double, _ times: Int) -> (Double, Double) {
  switch times % 4 {
  case 1: return (y, 1 - x)        // image was rotated 90° clockwise
  case 3: return (1 - y, x)        // image was rotated 270° clockwise
  default: return (x, y)
  }
}

guard CommandLine.arguments.count > 1,
      let ns = NSImage(contentsOfFile: CommandLine.arguments[1]),
      let base = ns.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
  FileHandle.standardError.write("cannot load image\n".data(using: .utf8)!); exit(1)
}
var rows: [[String: Any]] = []
// Whole image plus overlapping N x N tiles; N grows with the sheet size (~1,800 px per tile) so
// small schedule text on large sheets keeps enough pixels per glyph. Rotated passes (vertical
// tags) use 2 x 2 tiles.
func grid(_ n: Int) -> [CGRect] {
  let step = 1.0 / Double(n), pad = min(0.08, step * 0.25)
  return (0..<(n * n)).map { i in
    let x0 = max(0, Double(i % n) * step - pad), y0 = max(0, Double(i / n) * step - pad)
    return CGRect(x: x0, y: y0, width: min(1, Double(i % n + 1) * step + pad) - x0, height: min(1, Double(i / n + 1) * step + pad) - y0)
  }
}
let n = max(2, Int((Double(max(base.width, base.height)) / 1800).rounded(.up)))
let full = CGRect(x: 0, y: 0, width: 1, height: 1)
for times in [0, 1, 3] {
  guard let img = rotated(base, clockwise90: times) else { continue }
  for roi in [full] + grid(times == 0 ? n : 2) {
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = false
    req.minimumTextHeight = 0
    req.regionOfInterest = roi  // bottom-left origin, normalized
    try? VNImageRequestHandler(cgImage: img, options: [:]).perform([req])
    for obs in req.results ?? [] {
      guard let top = obs.topCandidates(1).first else { continue }
      let r = obs.boundingBox  // relative to roi, bottom-left origin
      let minX = roi.minX + r.minX * roi.width, maxX = roi.minX + r.maxX * roi.width
      let minY = roi.minY + r.minY * roi.height, maxY = roi.minY + r.maxY * roi.height
      let (ax, ay) = unrotate(minX, 1 - maxY, times)
      let (bx, by) = unrotate(maxX, 1 - minY, times)
      rows.append(["text": top.string, "conf": Double(top.confidence), "rot": times * 90,
                   "box": [min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)]])
    }
  }
}
let data = try JSONSerialization.data(withJSONObject: rows)
print(String(data: data, encoding: .utf8)!)
