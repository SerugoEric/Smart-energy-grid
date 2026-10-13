"""Diagnostic: find the tinted dashboard panels in a screenshot.

usage: python probe_tints.py <png> <hex> [<hex> ...]
Prints the bounding box of every given colour so the number and position of
the panels can be checked without OCR.
"""
import sys
from PIL import Image

path = sys.argv[1]
targets = [tuple(int(c[j:j + 2], 16) for j in (1, 3, 5))
           for c in sys.argv[2:]]

im = Image.open(path).convert("RGB")
w, h = im.size
px = im.load()
cut = min(h, 1020)

for t in targets:
    xs, ys = [], []
    count = 0
    hist = {}
    for y in range(0, cut, 2):
        for x in range(0, w, 2):
            r, g, b = px[x, y]
            if abs(r - t[0]) <= 6 and abs(g - t[1]) <= 6 and abs(b - t[2]) <= 6:
                xs.append(x)
                ys.append(y)
                count += 1
                hist[y // 20] = hist.get(y // 20, 0) + 1
    if count:
        bands = [f"{k * 20}:{v}" for k, v in sorted(hist.items()) if v > 20]
        print(f"#{t[0]:02x}{t[1]:02x}{t[2]:02x}  pixels={count:6d}  "
              f"x={min(xs)}..{max(xs)}  y={min(ys)}..{max(ys)}")
        print("     y-bands(count>20): " + " ".join(bands))
    else:
        print(f"#{t[0]:02x}{t[1]:02x}{t[2]:02x}  NOT FOUND")
