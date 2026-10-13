"""Diagnostic: how much of a screenshot is non-white, band by band.

usage: python probe_density.py <png> [bands]
Used to check that a dashboard screenshot really contains rendered panels
all the way down, without needing OCR.
"""
import sys
from PIL import Image

path = sys.argv[1]
bands = int(sys.argv[2]) if len(sys.argv) > 2 else 10

im = Image.open(path).convert("RGB")
w, h = im.size
cut = min(h, 1020)
step = max(1, cut // bands)
px = im.load()
print(f"{path}  {w}x{h}  non-white density per {step}px band (y<{cut})")
for y0 in range(0, cut, step):
    y1 = min(y0 + step, cut)
    total = 0
    nonwhite = 0
    dark = 0
    colour = 0
    for y in range(y0, y1, 4):
        for x in range(0, w, 4):
            total += 1
            r, g, b = px[x, y]
            if r < 246 or g < 246 or b < 246:
                nonwhite += 1
            if r < 120 and g < 120 and b < 120:
                dark += 1
            if max(r, g, b) - min(r, g, b) > 40:
                colour += 1
    print(f"  y{y0:4d}-{y1:4d}  non-white {100.0 * nonwhite / total:5.1f}%   "
          f"dark {100.0 * dark / total:5.1f}%   "
          f"colour {100.0 * colour / total:5.1f}%")
