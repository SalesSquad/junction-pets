// Licensed public HB full-frame FOREGROUND PROPOSALS, never GT boxes.
// This is a read-only Apple Vision experiment: no private image directories,
// no camera, no OCR, no identity, no product authorization or model rollout.
// Input path must be a named task-owned RGB PNG inside the explicit scratch root.
import Foundation
import Vision
import CoreVideo

struct Box: Codable {
    let id: Int
    let x: Int
    let y: Int
    let width: Int
    let height: Int
    let areaPixels: Int
    let coverage: Double
}

struct Output: Codable {
    let schema: String
    let source: String
    let frame: String
    let detector: String
    let imageWidth: Int
    let imageHeight: Int
    let maskInstances: Int
    let proposals: [Box]
    let usesGroundTruth: Bool
    let physicalIdentityVerified: Bool
    let actionAuthorized: Bool
}

let args=CommandLine.arguments
guard args.count==7, args[1]=="--root", args[3]=="--frame", args[5]=="--output" else {
    fputs("Usage: LensHBProposal --root <task-dir> --frame <hb_scene_frame.png> --output <json>\n",stderr)
    exit(2)
}
let root=URL(fileURLWithPath:args[2]).standardizedFileURL
let frame=String(args[4])
let output=URL(fileURLWithPath:args[6]).standardizedFileURL
guard (root.path.hasPrefix("/private/tmp/chibi-hb-detector-") ||
       root.path.hasPrefix("/tmp/chibi-hb-detector-")),
      root.resolvingSymlinksInPath().path.hasPrefix("/private/tmp/chibi-hb-detector-"),
      frame.range(of:#"^hb_(05|09|10|11)_[0-9]{6}\.png$"#,
                  options:.regularExpression) != nil,
      output.path != root.appendingPathComponent(frame).path,
      FileManager.default.fileExists(atPath:root.path),
      output.deletingLastPathComponent().path == root.path,
      !FileManager.default.fileExists(atPath:output.path) else {
    fputs("Source outside task-owned PUBLIC frame root or output exists\n",stderr)
    exit(3)
}
let image=root.appendingPathComponent(frame).standardizedFileURL
guard image.deletingLastPathComponent().path==root.path,
      image.resolvingSymlinksInPath().deletingLastPathComponent().path ==
          root.resolvingSymlinksInPath().path,
      FileManager.default.fileExists(atPath:image.path),
      output.deletingLastPathComponent().path == root.path,
      !FileManager.default.fileExists(atPath:output.path) else {
    fputs("Unverified public source frame\n",stderr)
    exit(3)
}
do {
    let handler=VNImageRequestHandler(url:image,options:[:])
    let request=VNGenerateForegroundInstanceMaskRequest()
    try handler.perform([request])
    guard let result=request.results?.first else {
        let empty=Output(schema:"chibi.lens.hb.vision-proposal.v1",
            source:"BOP_HB_CC0_PUBLIC_RGB",frame:frame,
            detector:"AppleForegroundInstanceMask",imageWidth:0,imageHeight:0,maskInstances:0,proposals:[],
            usesGroundTruth:false,physicalIdentityVerified:false,actionAuthorized:false)
        try JSONEncoder().encode(empty).write(to:output,options:.atomic)
        print("NO_FOREGROUND_PROPOSALS")
        exit(0)
    }
    let instances=result.allInstances
    if instances.count>64 {
        fputs("Unexpected unbounded instances\n",stderr)
        exit(4)
    }
    var proposalBoxes=[Box]()
    var outputWidth=0
    var outputHeight=0
    for instance in instances {
        let mask=try result.generateScaledMaskForImage(
            forInstances:IndexSet(integer:instance),from:handler)
        let width=CVPixelBufferGetWidth(mask)
        let height=CVPixelBufferGetHeight(mask)
        if width<=0 || height<=0 || width>5000 || height>5000 {
            throw NSError(domain:"HBProposal",code:4)
        }
        if outputWidth>0 && (outputWidth != width || outputHeight != height) {
            throw NSError(domain:"HBProposal",code:5)
        }
        outputWidth=width;outputHeight=height
        let format=CVPixelBufferGetPixelFormatType(mask)
        let fourcc = [24,16,8,0].map { shift in
            String(UnicodeScalar(UInt8((format >> UInt32(shift)) & 0xff)))
        }.joined()
        if format != kCVPixelFormatType_OneComponent8 &&
           format != kCVPixelFormatType_32BGRA &&
           format != kCVPixelFormatType_OneComponent32Float {
            fputs("Unsupported Vision mask pixel format=\(fourcc) (\(format))\n",stderr)
            throw NSError(domain:"HBProposal",code:6)
        }
        print("PUBLIC_MASK_PIXEL_FORMAT=\(fourcc)")
        CVPixelBufferLockBaseAddress(mask, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(mask,.readOnly) }
        guard let base=CVPixelBufferGetBaseAddress(mask) else {
            throw NSError(domain:"HBProposal",code:7)
        }
        let pitch=CVPixelBufferGetBytesPerRow(mask)
        let bytes=base.assumingMemoryBound(to:UInt8.self)
        var left=width;var top=height;var right = -1;var bottom = -1
        var area=0
        for y in 0..<height {
            let row=bytes.advanced(by:y*pitch)
            for x in 0..<width {
                let foreground:Bool
                if format==kCVPixelFormatType_OneComponent8 {
                    foreground=row[x]>127
                } else if format==kCVPixelFormatType_32BGRA {
                    foreground=row[x*4+3]>127
                } else {
                    let scalars=UnsafeRawPointer(base).advanced(by:y*pitch)
                         .assumingMemoryBound(to:Float.self)
                    foreground=scalars[x].isFinite && scalars[x]>0.5
                }
                if foreground {
                    left=min(left,x);top=min(top,y)
                    right=max(right,x);bottom=max(bottom,y)
                    area+=1
                }
            }
        }
        if area<max(225,width*height/2000) || right<left || bottom<top {continue}
        let box=Box(id:instance,x:left,y:top,width:right-left+1,
                    height:bottom-top+1,areaPixels:area,
                    coverage:Double(area)/Double(width*height))
        proposalBoxes.append(box)
    }
    proposalBoxes.sort { $0.areaPixels > $1.areaPixels }
    if proposalBoxes.count>16 {
        proposalBoxes=Array(proposalBoxes.prefix(16))
    }
    let resultOutput=Output(schema:"chibi.lens.hb.vision-proposal.v1",
       source:"BOP_HB_CC0_PUBLIC_RGB",frame:frame,
       detector:"AppleForegroundInstanceMask",imageWidth:outputWidth,imageHeight:outputHeight,
       maskInstances:instances.count,proposals:proposalBoxes,
       usesGroundTruth:false,physicalIdentityVerified:false,
       actionAuthorized:false)
    let encoder=JSONEncoder()
    encoder.outputFormatting=[.sortedKeys]
    try encoder.encode(resultOutput).write(to:output,options:.atomic)
    print("PUBLIC_FOREGROUND_PROPOSALS=\(proposalBoxes.count)")
} catch {
    fputs("Apple Vision foreground proposal failed: \(error)\n",stderr)
    exit(6)
}
