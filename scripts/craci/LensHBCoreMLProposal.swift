// Pretrained detector baseline: Apple's public YOLOv3TinyFP16 Core ML model.
// Research only, no private images, no identity claim or commercial license
// assumption. GT BOP boxes/masks are not inputs. Training/evaluation remain
// separated: this outputs candidate boxes from raw full-frame RGB ONLY.
import Foundation
import Vision
import CoreML
import ImageIO

struct Box: Codable {
    let id:Int
    let x:Int
    let y:Int
    let width:Int
    let height:Int
    let areaPixels:Int
    let coverage:Double
    let predictedCOCOLabel:String
    let confidence:Double
}
struct Result: Codable {
    let schema:String
    let source:String
    let frame:String
    let detector:String
    let modelSource:String
    let imageWidth:Int
    let imageHeight:Int
    let maskInstances:Int
    let proposals:[Box]
    let usesGroundTruth:Bool
    let physicalIdentityVerified:Bool
    let actionAuthorized:Bool
}

let args=CommandLine.arguments
guard args.count==9,args[1]=="--root",args[3]=="--frame",
      args[5]=="--model",args[7]=="--output" else {
    fputs("Usage: LensHBCoreMLProposal --root scratch --frame hb_05_000000.png --model AppleYolo.mlmodelc --output result.json\n",stderr)
    exit(2)
}
let root=URL(fileURLWithPath:args[2]).standardizedFileURL
let frame=String(args[4])
let model=URL(fileURLWithPath:args[6]).standardizedFileURL
let output=URL(fileURLWithPath:args[8]).standardizedFileURL
guard (root.path.hasPrefix("/private/tmp/chibi-hb-detector-") ||
       root.path.hasPrefix("/tmp/chibi-hb-detector-")),
      root.resolvingSymlinksInPath().path.hasPrefix("/private/tmp/chibi-hb-detector-"),
      (model.path.hasPrefix("/private/tmp/chibi-hb-detector-models-20261114/") ||
       model.path.hasPrefix("/tmp/chibi-hb-detector-models-20261114/")),
      model.pathExtension=="mlmodelc",
      frame.range(of:#"^hb_(05|09|10|11)_[0-9]{6}\.png$"#,
                  options:.regularExpression) != nil,
      output.deletingLastPathComponent().path == root.path,
      !FileManager.default.fileExists(atPath:output.path) else {
    fputs("Untrusted public source/model path or output exists\n",stderr)
    exit(3)
}
let image=root.appendingPathComponent(frame).standardizedFileURL
guard image.deletingLastPathComponent().path==root.path,
      image.resolvingSymlinksInPath().deletingLastPathComponent().path ==
          root.resolvingSymlinksInPath().path,
      FileManager.default.fileExists(atPath:image.path),
      FileManager.default.fileExists(atPath:model.path),
      let src=CGImageSourceCreateWithURL(image as CFURL,nil),
      let cg=CGImageSourceCreateImageAtIndex(src,0,nil) else {
    fputs("Missing validated public image or CoreML model\n",stderr)
    exit(4)
}
let width=cg.width
let height=cg.height
guard 200<=width && width<=3000 && 200<=height && height<=3000 else {
    fputs("Unbounded input camera dimensions\n",stderr)
    exit(4)
}
do {
    let cfg=MLModelConfiguration()
    cfg.computeUnits = .all
    let mlModel=try MLModel(contentsOf:model,configuration:cfg)
    let vnModel=try VNCoreMLModel(for:mlModel)
    let req=VNCoreMLRequest(model:vnModel)
    req.imageCropAndScaleOption = .scaleFit
    let handler=VNImageRequestHandler(cgImage:cg,options:[:])
    try handler.perform([req])
    guard let recognized=req.results as? [VNRecognizedObjectObservation] else {
        fputs("Pretrained CoreML model did not return recognized object boxes\n",stderr)
        exit(5)
    }
    if recognized.count>1000 {
        fputs("Unbounded pretrained object proposal result\n",stderr)
        exit(5)
    }
    var proposals=[Box]()
    for (i,o) in recognized.enumerated() {
        guard let best=o.labels.first else { continue }
        if best.confidence < 0.15 { continue }
        let r=o.boundingBox
        if !r.minX.isFinite || !r.minY.isFinite || !r.maxX.isFinite || !r.maxY.isFinite {
            throw NSError(domain:"CoreMLProposal",code:6)
        }
        let left=max(0,min(width-1,Int(r.minX*Double(width))))
        let top=max(0,min(height-1,Int((1-r.maxY)*Double(height))))
        let right=max(0,min(width,Int(ceil(r.maxX*Double(width)))))
        let bottom=max(0,min(height,Int(ceil((1-r.minY)*Double(height)))))
        let bw=right-left
        let bh=bottom-top
        if bw<14 || bh<14 {continue}
        let area=bw*bh
        proposals.append(Box(id:i+1,x:left,y:top,width:bw,height:bh,
             areaPixels:area,coverage:Double(area)/Double(width*height),
             predictedCOCOLabel:String(best.identifier),confidence:Double(best.confidence)))
    }
    proposals.sort { $0.confidence > $1.confidence }
    if proposals.count>32 { proposals=Array(proposals.prefix(32)) }
    let record=Result(schema:"chibi.lens.hb.vision-proposal.v1",
         source:"BOP_HB_CC0_PUBLIC_RGB",frame:frame,
         detector:"AppleCoreML_YOLOv3TinyFP16",
         modelSource:"AppleMLResearchModel_NO_DEPLOYMENT_RIGHTS_ASSUMED",
         imageWidth:width,imageHeight:height,
         maskInstances:recognized.count,proposals:proposals,
         usesGroundTruth:false,physicalIdentityVerified:false,actionAuthorized:false)
    let encoder=JSONEncoder()
    encoder.outputFormatting=[.sortedKeys]
    try encoder.encode(record).write(to:output,options:.atomic)
    print("PUBLIC_COREML_YOLO_PROPOSALS=\(proposals.count)")
} catch {
    fputs("Pretrained Apple Core ML proposal inference failed: \(error)\n",stderr)
    exit(6)
}
