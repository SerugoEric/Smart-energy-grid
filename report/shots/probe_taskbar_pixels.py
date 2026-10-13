from PIL import Image
from collections import Counter
import sys

im = Image.open(sys.argv[1]).convert("RGB")
W, H = im.size
px = im.load()

y0 = int(sys.argv[2]) if len(sys.argv) > 2 else 680
y1 = int(sys.argv[3]) if len(sys.argv) > 3 else 720

c = Counter()
for y in range(y0, y1):
    for x in range(0, W):
        c[px[x, y]] += 1
print(f"band y{y0}-{y1}: {len(c)} distinct colours")
for col, n in c.most_common(12):
    print(f"   {col}  {n}")

dom = c.most_common(1)[0][0]
xs = Counter()
for y in range(y0, y1):
    for x in range(0, W):
        if px[x, y] != dom:
            xs[x // 60 * 60] += 1
print("non-dominant x buckets:", dict(sorted(xs.items())))
