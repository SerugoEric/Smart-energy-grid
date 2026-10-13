"""Sanity-check a report screenshot without needing OCR.

Reports whether the pinned console window covers only the screen, how much
text-like content it holds, and whether the taskbar/clock strip is present.
"""
import sys
from PIL import Image

path = sys.argv[1]
win_w, win_h = 1261, 549

im = Image.open(path).convert("RGB")
W, H = im.size
px = im.load()

bright = 0
rows = 0
for y in range(0, min(win_h, H)):
    c = 0
    for x in range(0, min(win_w, W)):
        r, g, b = px[x, y]
        if r + g + b > 330:
            c += 1
    bright += c
    if c > 20:
        rows += 1

strip = 0
for y in range(max(0, H - 30), H):
    for x in range(max(0, W - 130), W):
        r, g, b = px[x, y]
        if r + g + b > 250:
            strip += 1

print(f"file        : {path}")
print(f"size        : {W} x {H}")
print(f"window area : {win_w} x {win_h}  fits={W >= win_w and H >= win_h}")
print(f"text pixels : {bright}")
print(f"rows w/ text: {rows}")
print(f"clock strip : {strip}")
