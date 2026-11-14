// Frozen Apple Vision feature vectors for CC0 BOP HomebrewedDB object crops.
// Reads only explicit, local temp files listed in task-owned TSV. Never opens
// cameras, OCR, personal screenshots, network, iCloud or product databases.
// A run emits numerical JSONL, with no image path or pixels in output.
// macOS 27 Vision revision 2; macOS and device precision are recorded.
import Foundation
import Vision

struct Record: Codable {
    let row_id: String
    let source: String
    let vision_revision: Int
    let vision_element_type: String
    let elements: Int
    let embedding: [Float]
}

enum Failure: Error {
    case invalidArgs
    case invalidManifest
    case invalidPixelBuffer
    case failedVector
}

let args=CommandLine.arguments
guard args.count==5, args[1]=="--manifest", args[3]=="--output" else {
    fputs("Usage: LensHBFeaturePrint --manifest /absolute/path/list.tsv --output /absolute/path/features.jsonl\n",stderr)
    exit(2)
}
let manifestURL=URL(fileURLWithPath:args[2])
let outputURL=URL(fileURLWithPath:args[4])
guard manifestURL.isFileURL,outputURL.isFileURL,
      outputURL.path != manifestURL.path,
      !FileManager.default.fileExists(atPath: outputURL.path) else {
    fputs("Refuse to replace output or use non-file sources\n",stderr)
    exit(2)
}
let content: String
do { content=try String(contentsOf:manifestURL,encoding:.utf8) }
catch { fputs("Read failure\n",stderr);exit(3) }
let lines=content.split(separator:"\n",omittingEmptySubsequences:true)
guard !lines.isEmpty, lines.count<=4000 else {
    fputs("Empty or unbounded manifest\n",stderr)
    exit(2)
}
let fm=FileManager.default
let root=manifestURL.deletingLastPathComponent().standardizedFileURL
let outPath=outputURL.path
guard fm.createFile(atPath:outPath,contents:nil,attributes:[.posixPermissions:0o600]),
      let handle=FileHandle(forWritingAtPath:outPath) else {
    fputs("Output open failed\n",stderr);exit(4)
}
defer { try? handle.close() }
let encoder=JSONEncoder()
encoder.outputFormatting=[.sortedKeys]
var counted=0
var seenRowIds=Set<String>()
for line in lines {
    let parts=line.split(separator:"\t",omittingEmptySubsequences:false)
    guard parts.count==2 else { fputs("Malformed manifest\n",stderr);exit(5) }
    let rowId=String(parts[0])
    let relative=String(parts[1])
    // New scene8 PUBLIC-only OOD contract. Reject ALL legacy train/cal/test scenes and path traversal.
    guard rowId.range(of:#"^hb_08_[0-9]{6}_(11|15|22|24|31|32)$"#,
                      options:.regularExpression) != nil,
          relative == rowId + ".png",
          !seenRowIds.contains(rowId),
          relative.range(of:#"^[a-zA-Z0-9_-]+\.png$"#,
                         options:.regularExpression) != nil else {
        fputs("Unsafe input row or filename\n",stderr)
        exit(5)
    }
    let imageURL=root.appendingPathComponent(relative).standardizedFileURL
    let canonicalRoot=root.resolvingSymlinksInPath()
    let canonicalImage=imageURL.resolvingSymlinksInPath()
    let imageAttributes=try? imageURL.resourceValues(forKeys:
        [.isSymbolicLinkKey,.isRegularFileKey])
    guard imageURL.deletingLastPathComponent().path == root.path,
          canonicalImage.deletingLastPathComponent().path == canonicalRoot.path,
          imageAttributes?.isSymbolicLink == false,
          imageAttributes?.isRegularFile == true,
          fm.fileExists(atPath:imageURL.path),
          !imageURL.path.contains("/../") else {
        fputs("Not a resident owned public image\n",stderr)
        exit(5)
    }
    seenRowIds.insert(rowId)
    autoreleasepool {
        do {
            let request=VNGenerateImageFeaturePrintRequest()
            request.revision=2
            request.imageCropAndScaleOption = .scaleFit
            try VNImageRequestHandler(url:imageURL,options:[:]).perform([request])
            guard let observation=request.results?.first,
                  observation.elementType == .float,
                  observation.elementCount>0 && observation.elementCount<=4096,
                  observation.data.count == observation.elementCount * MemoryLayout<Float>.size else {
                throw Failure.failedVector
            }
            let vector=observation.data.withUnsafeBytes { bytes -> [Float] in
                (0..<observation.elementCount).map {
                    bytes.loadUnaligned(fromByteOffset:$0*MemoryLayout<Float>.size,as:Float.self)
                }
            }
            guard vector.allSatisfy({$0.isFinite}) else {throw Failure.failedVector}
            let output=Record(row_id:rowId,source:"PUBLIC_HB_CC0",vision_revision:2,
                              vision_element_type:"float32",elements:vector.count,embedding:vector)
            var serialized=try encoder.encode(output)
            serialized.append(10)
            try handle.write(contentsOf:serialized)
            counted += 1
        } catch {
            fputs("Vision feature extraction rejected one source row\n",stderr)
            exit(6)
        }
    }
}
print("HB_VISION_PUBLIC_CROPS=\(counted)")
