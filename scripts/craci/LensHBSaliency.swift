// Bounded source-only Apple Vision objectness proposals on full public RGB frames.
// Does not use BOP annotation or object bounding box as input, no identity/consent.
import Foundation
import Vision
import ImageIO

struct Proposal: Codable {
    let id:Int
    let x:Int
    let y:Int
    let width:Int
    let height:Int
    let areaPixels:Int
    let coverage:Double
}

struct Result: Codable {
    let schema:String
    let source:String
    let frame:String
    let detector:String
    let imageWidth:Int
    let imageHeight:Int
    let maskInstances:Int
    let proposals:[Proposal]
    let usesGroundTruth:Bool
    let physicalIdentityVerified:Bool
    let actionAuthorized:Bool
}

let args=CommandLine.arguments
guard args.count==7,args[1]=="--root",args[3]=="--frame",args[5]=="--output" else {
    fputs("Usage: LensHBSaliency --root scratch --frame hb_05_000000.png --output result.json\n",stderr)
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
      output.deletingLastPathComponent().path == root.path,
      !FileManager.default.fileExists(atPath:output.path) else {
    fputs("Untrusted public source frame path or existing output\n",stderr)
    exit(3)
}
let image=root.appendingPathComponent(frame).standardizedFileURL
guard image.deletingLastPathComponent().path==root.path,
      image.resolvingSymlinksInPath().deletingLastPathComponent().path ==
          root.resolvingSymlinksInPath().path,
      FileManager.default.fileExists(atPath:image.path),
      let src=CGImageSourceCreateWithURL(image as CFURL,nil),
      let source=CGImageSourceCreateImageAtIndex(src,0,nil) else {
    fputs("Source image outside licensed task scratch or not decoded\n",stderr)
    exit(4)
}
let width=source.width
let height=source.height
guard 200<=width && width<=3000 && 200<=height && height<=3000 else {
    fputs("Unbounded input pixel dimensions\n",stderr)
    exit(4)
}
do {
    let request=VNGenerateObjectnessBasedSaliencyImageRequest()
    let handler=VNImageRequestHandler(cgImage:source,options:[:])
    try handler.perform([request])
    let objects=request.results?.first?.salientObjects ?? []
    if objects.count>32 {fputs("Unbounded saliency objects\n",stderr);exit(5)}
    var proposals=[Proposal]()
    for (i, obj) in objects.enumerated() {
        let r=obj.boundingBox
        if !(r.minX.isFinite && r.maxX.isFinite &&
             r.minY.isFinite && r.maxY.isFinite) {
            fputs("Invalid saliency result\n",stderr);exit(5)
        }
        let minX=max(0,min(width-1,Int(r.minX * Double(width))))
        let minY=max(0,min(height-1,Int((1-r.maxY) * Double(height))))
        let maxX=max(0,min(width,Int(ceil(r.maxX*Double(width)))))
        let maxY=max(0,min(height,Int(ceil((1-r.minY)*Double(height)))))
        let w=maxX-minX
        let h=maxY-minY
        if w<14 || h<14 {continue}
        let area=w*h
        proposals.append(Proposal(id:i+1,x:minX,y:minY,width:w,height:h,
           areaPixels:area,coverage:Double(area)/Double(width*height)))
    }
    let result=Result(schema:"chibi.lens.hb.vision-proposal.v1",
        source:"BOP_HB_CC0_PUBLIC_RGB",frame:frame,
        detector:"AppleObjectnessBasedSaliency",imageWidth:width,imageHeight:height,
        maskInstances:objects.count,proposals:proposals,
        usesGroundTruth:false,physicalIdentityVerified:false,actionAuthorized:false)
    let encoder=JSONEncoder()
    encoder.outputFormatting=[.sortedKeys]
    try encoder.encode(result).write(to:output,options:.atomic)
    print("PUBLIC_SALIENCY_PROPOSALS=\(proposals.count)")
} catch {
    fputs("Objectness saliency inference failure: \(error)\n",stderr)
    exit(6)
}
