from PIL import Image
from collections import Counter
import sys

im = Image.open(sys.argv[1]).convert("RGB")
px = im.load()

def stats(x0, x1, y0, y1, label):
    c = Counter()
    for y in range(y0, y1):
        for x in range(x0, x1):
            c[px[x, y]] += 1
    print(f"--- {label} ({x0},{y0})-({x1},{y1})")
    for col, n in c.most_common(6):
        print(f"    {col}  {n}")

stats(1150, 1280, 688, 720, "bottom-right clock strip")
stats(0, 400, 688, 720, "bottom-left taskbar")
stats(0, 1280, 560, 660, "desktop below window")
