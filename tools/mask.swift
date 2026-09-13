import Foundation
import Vision
import CoreImage
import CoreImage.CIFilterBuiltins
import AppKit

let src = URL(fileURLWithPath: CommandLine.arguments[1])
let out = URL(fileURLWithPath: CommandLine.arguments[2])
let handler = VNImageRequestHandler(url: src)
let req = VNGenerateForegroundInstanceMaskRequest()
try handler.perform([req])
guard let obs = req.results?.first else { print("no foreground"); exit(1) }
print("instances:", obs.allInstances.count)
let buf = try obs.generateScaledMaskForImage(forInstances: obs.allInstances, from: handler)
let ci = CIImage(cvPixelBuffer: buf)
let ctx = CIContext()
try ctx.writePNGRepresentation(of: ci, to: out, format: .L8, colorSpace: CGColorSpaceCreateDeviceGray())
print("ok", ci.extent)
