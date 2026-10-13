from PIL import Image
import sys

im = Image.open(sys.argv[1]).convert("RGB")
W, H = im.size
cols, rows = 80, 36
px = im.load()
chars = " .:-=+*#%@"
print(f"{W}x{H} -> {cols}x{rows}")
for ry in range(rows):
    line = ""
    for rx in range(cols):
        x0 = rx * W // cols
        x1 = (rx + 1) * W // cols
        y0 = ry * H // rows
        y1 = (ry + 1) * H // rows
        tot = 0
        n = 0
        for y in range(y0, y1, 2):
            for x in range(x0, x1, 2):
                r, g, b = px[x, y]
                tot += r + g + b
                n += 1
        avg = tot / max(n, 1)
        idx = min(int(avg / 765 * (len(chars) - 1) * 6), len(chars) - 1)
        line += chars[idx]
    print(line)
