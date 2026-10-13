"""Coarse ASCII rendering of a screenshot so the layout can be inspected without OCR."""
import sys
from PIL import Image

path = sys.argv[1] if len(sys.argv) > 1 else r"report\screenshots\7_1_dashboard_raw.png"
cols = int(sys.argv[2]) if len(sys.argv) > 2 else 96
rows = int(sys.argv[3]) if len(sys.argv) > 3 else 40
crop = [int(v) for v in sys.argv[4:8]] if len(sys.argv) >= 8 else None

im = Image.open(path).convert("RGB")
if crop:
    im = im.crop((crop[0], crop[1], crop[2], crop[3]))
w, h = im.size
px = im.load()

tints = {
    "r": (255, 233, 233),
    "g": (233, 255, 233),
    "b": (233, 233, 255),
    "o": (255, 243, 224),
    "p": (243, 233, 255),
}


def classify(cell):
    r = g = b = n = 0
    dark = white = grey = 0
    for y in range(cell[1], cell[3]):
        for x in range(cell[0], cell[2]):
            pr, pg, pb = px[x, y]
            r += pr
            g += pg
            b += pb
            n += 1
            lum = (pr + pg + pb) / 3
            if lum < 140:
                dark += 1
            elif lum > 245:
                white += 1
            else:
                grey += 1
    r, g, b = r / n, g / n, b / n
    for k, (tr, tg, tb) in tints.items():
        if abs(r - tr) < 7 and abs(g - tg) < 7 and abs(b - tb) < 7:
            return k
    if dark > n * 0.10:
        return "#"
    if white > n * 0.85:
        return "."
    if grey > n * 0.5:
        return "+"
    return "?"


print(f"{path}  {w}x{h}  cell={w // cols}x{h // rows}")
hdr = "    " + "".join(str((i * w // cols) // 100 % 10) for i in range(cols))
hdr2 = "    " + "".join(str((i * w // cols) // 10 % 10) for i in range(cols))
print(hdr)
print(hdr2)
for ry in range(rows):
    y0 = ry * h // rows
    y1 = (ry + 1) * h // rows
    line = []
    for rx in range(cols):
        x0 = rx * w // cols
        x1 = (rx + 1) * w // cols
        line.append(classify((x0, y0, x1, y1)))
    print(f"{y0:4d}" + "".join(line))
