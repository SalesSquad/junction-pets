// Render page 1 of a drawing PDF and extract its text layer (macOS PDFKit; no network).
// Usage: pdf-sheet <pdf> <out.jpg> <maxPixels>
// Prints JSON {width,height,rotation,words:[{text,box:[x0,y0,x1,y1]}]} with boxes normalized to
// the displayed (rotated) page, origin top-left. Words come from the PDF text layer only.
import AppKit
import Foundation
import PDFKit

let args = CommandLine.arguments
guard args.count >= 4, let doc = PDFDocument(url: URL(fileURLWithPath: args[1])), let page = doc.page(at: 0) else {
  FileHandle.standardError.write("cannot open pdf\n".data(using: .utf8)!); exit(1)
}
let maxPx = CGFloat(Double(args[3]) ?? 3584)
let box = page.bounds(for: .mediaBox)
let rot = ((page.rotation % 360) + 360) % 360
let (dw, dh) = rot % 180 == 0 ? (box.width, box.height) : (box.height, box.width)
let scale = maxPx / max(dw, dh)
let img = page.thumbnail(of: NSSize(width: dw * scale, height: dh * scale), for: .mediaBox)
if let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
   let jpg = rep.representation(using: .jpeg, properties: [.compressionFactor: 0.65]) {
  try jpg.write(to: URL(fileURLWithPath: args[2]))
}
func display(_ u: CGFloat, _ v: CGFloat) -> (CGFloat, CGFloat) {
  switch rot { case 90: return (1 - v, u); case 180: return (1 - u, 1 - v); case 270: return (v, 1 - u); default: return (u, v) }
}
var words: [[String: Any]] = []
if let text = page.string {
  let ns = text as NSString
  // Whitespace-delimited tokens keep drawing notation intact (3'-0", 107.A, AL-2/GL-2).
  let tokenRx = try NSRegularExpression(pattern: "\\S+")
  for m in tokenRx.matches(in: text, range: NSRange(location: 0, length: ns.length)) {
    let range = m.range
    guard let sel = page.selection(for: range) else { continue }
    let r = sel.bounds(for: page)
    if r.width <= 0 || r.height <= 0 { continue }
    let w = ns.substring(with: range)
    let u0 = (r.minX - box.minX) / box.width, u1 = (r.maxX - box.minX) / box.width
    let v0 = 1 - (r.maxY - box.minY) / box.height, v1 = 1 - (r.minY - box.minY) / box.height
    let (ax, ay) = display(u0, v0), (bx, by) = display(u1, v1)
    words.append(["text": w, "box": [min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)].map { Double($0) }])
  }
}
let out: [String: Any] = ["width": Int(dw * scale), "height": Int(dh * scale), "rotation": rot, "words": words]
print(String(data: try JSONSerialization.data(withJSONObject: out), encoding: .utf8)!)
