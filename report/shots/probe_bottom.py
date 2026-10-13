from PIL import Image
import sys

im = Image.open(sys.argv[1]).convert("RGB")
px = im.load()
print("y    bright(x1000-1279)  bright(x0-1279)")
for y in range(630, 720, 3):
    a = sum(1 for x in range(1000, 1280) if sum(px[x, y]) > 250)
    b = sum(1 for x in range(0, 1280) if sum(px[x, y]) > 250)
    print(f"{y:3d}  {a:5d}  {b:5d}")
