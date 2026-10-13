"""Diagnostic: locate the panel borders of the dashboard screenshot.

The dashboard gives every graph a light grey border, so the number and
position of the panels can be checked without OCR: long horizontal and
vertical runs of that grey are the panel edges.

usage: python probe_panels.py <png>
"""
import sys
from PIL import Image

path = sys.argv[1]
im = Image.open(path).convert("RGB")
w, h = im.size
px = im.load()
cut = min(h, 1020)

TARGET = (208, 208, 208)
TOL = 18


def is_border(x, y):
    r, g, b = px[x, y]
    return (abs(r - TARGET[0]) <= TOL and abs(g - TARGET[1]) <= TOL
            and abs(b - TARGET[2]) <= TOL)


rows = []
for y in range(cut):
    run = 0
    best = 0
    for x in range(w):
        if is_border(x, y):
            run += 1
            best = max(best, run)
        else:
            run = 0
    if best >= 250:
        rows.append((y, best))

cols = []
for x in range(w):
    run = 0
    best = 0
    for y in range(cut):
        if is_border(x, y):
            run += 1
            best = max(best, run)
        else:
            run = 0
    if best >= 150:
        cols.append((x, best))

print(f"{path}  {w}x{h}")
print("horizontal border lines (y, longest run):")
for y, run in rows:
    print(f"   y={y:4d}  run={run}")
print("vertical border lines (x, longest run):")
for x, run in cols:
    print(f"   x={x:4d}  run={run}")

print("vertical extent of each detected vertical border:")
for x, run in cols:
    runs = []
    start = None
    for y in range(cut):
        if is_border(x, y):
            if start is None:
                start = y
        else:
            if start is not None and y - start >= 40:
                runs.append((start, y - 1))
            start = None
    if start is not None and cut - start >= 40:
        runs.append((start, cut - 1))
    print(f"   x={x:4d}  segments={runs}")
