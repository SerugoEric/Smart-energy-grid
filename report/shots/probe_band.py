from PIL import Image
import sys
from collections import Counter

im = Image.open(sys.argv[1]).convert("RGB")
W, H = im.size
px = im.load()

# What dominates each band?
for y0 in range(600, 720, 10):
    c = Counter()
    for y in range(y0, min(y0 + 10, H)):
        for x in range(0, W):
            c[px[x, y]] += 1
    total = sum(c.values())
    top = ", ".join(f"{col}:{n}" for col, n in c.most_common(3))
    other = total - c.most_common(1)[0][1]
    print(f"y {y0:3d}-{y0+9:3d}  dominant={c.most_common(1)[0][0]}  non-dominant={other}  | {top}")

# Column profile of any non-dominant pixel in the bottom 60 rows
dom = Counter()
for y in range(660, H):
    for x in range(0, W):
        dom[px[x, y]] += 1
d = dom.most_common(1)[0][0]
hits = Counter()
for y in range(660, H):
    for x in range(0, W):
        if px[x, y] != d:
            hits[x // 40 * 40] += 1
print("bottom-60 non-dominant pixels by x bucket:", dict(sorted(hits.items())))
