"""Render an OCR-only view and return its inverse transform."""
import json
import math
import sys
from PIL import Image

source, target, angle, scale, *crop = sys.argv[1:]
angle, scale = float(angle), int(scale)
with Image.open(source) as original:
    image = Image.new("RGBA", original.size, "white")
    image.alpha_composite(original.convert("RGBA"))
    image = image.convert("RGB")
if crop:
    from PIL import ImageOps
    image = ImageOps.expand(image.crop(tuple(map(int, crop))), border=4, fill="white")
width, height = image.size
view = image.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor="white")
if scale != 1:
    view = view.resize((width * scale, height * scale), Image.Resampling.LANCZOS)
view.save(target)
radians = math.radians(angle)
cosine, sine = math.cos(radians), math.sin(radians)
cx, cy = width / 2, height / 2
print(json.dumps([cosine / scale, -sine / scale, cx - cosine * cx + sine * cy,
                  sine / scale, cosine / scale, cy - sine * cx - cosine * cy]))
