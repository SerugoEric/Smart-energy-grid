from PIL import Image
import sys

im = Image.open(sys.argv[1]).convert("RGB")
px = im.load()
x0, x1 = int(sys.argv[2]), int(sys.argv[3])
y0, y1 = int(sys.argv[4]), int(sys.argv[5])
step = int(sys.argv[6]) if len(sys.argv) > 6 else 2

chars = " .:-=+*#%@"
print(f"region x{x0}-{x1} y{y0}-{y1} step={step}")
for y in range(y0, y1, step):
    line = ""
    for x in range(x0, x1, step):
        r, g, b = px[x, y]
        v = (r + g + b) / 3
        line += chars[min(int(v / 255 * 9), 9)]
    print(f"{y:3d} {line}")
