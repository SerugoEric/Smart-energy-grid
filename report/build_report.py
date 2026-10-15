import base64
import pathlib
import re
import subprocess
import sys

import markdown

HERE = pathlib.Path(__file__).resolve().parent
MD = HERE / "Assignment_I_Report.md"
HTML = HERE / "Assignment_I_Report.html"
PDF = HERE / "Assignment_I_Report.pdf"

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

CSS = """
@page { size: A4; margin: 16mm 14mm; }
html { -webkit-print-color-adjust: exact; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 10.5pt;
       line-height: 1.4; color: #1a1a1a; margin: 0; }
h1 { font-size: 18pt; border-bottom: 2px solid #1f6feb; padding-bottom: 4px;
     margin-top: 0; color: #0b3d91; page-break-before: always; }
h1:first-of-type { page-break-before: avoid; }
h2 { font-size: 14pt; color: #0b3d91; margin-top: 18px;
     border-bottom: 1px solid #cfd8e3; padding-bottom: 2px; }
h3 { font-size: 12pt; color: #244; }
img { display: block; max-width: 100%; max-height: 155mm; margin: 8px auto;
      border: 1px solid #b9c2cc; padding: 2px; background: #fff; }
em { color: #444; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 14px 0;
        font-size: 9pt; page-break-inside: avoid; }
th, td { border: 1px solid #b9c2cc; padding: 4px 6px; text-align: left;
         vertical-align: top; }
th { background: #eef3fb; }
tr:nth-child(even) td { background: #f8fafc; }
code { background: #f1f4f8; padding: 1px 3px; border-radius: 3px;
       font-family: Consolas, monospace; font-size: 9pt; }
blockquote { border-left: 3px solid #1f6feb; margin: 8px 0; padding: 2px 12px;
             background: #f7fafd; color: #334; }
.pagebreak { page-break-after: always; height: 0; }
.missing { border: 2px dashed #c0392b; background: #fdf3f2; color: #8a2b20;
           padding: 10px 12px; margin: 10px 0; font-weight: 600; }
"""


def inline_images(html: str) -> str:
    """Embed local images as data URIs so the PDF is self-contained."""
    def repl(m):
        src = m.group(1)
        p = (HERE / src).resolve()
        if not p.exists():
            return m.group(0)
        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
        data = base64.b64encode(p.read_bytes()).decode("ascii")
        return 'src="data:%s;base64,%s"' % (mime, data)
    return re.sub(r'src="([^"]+)"', repl, html)


def main():
    text = MD.read_text(encoding="utf-8")
    body = markdown.markdown(
        text, extensions=["tables", "fenced_code", "attr_list", "sane_lists"]
    )
    body = inline_images(body)
    html = ("<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Smart Energy Grid Analytics - Assignment I</title>"
            "<style>%s</style></head><body>%s</body></html>" % (CSS, body))
    HTML.write_text(html, encoding="utf-8")
    print("wrote", HTML)

    edge = next((e for e in EDGE_CANDIDATES if pathlib.Path(e).exists()), None)
    if not edge:
        print("Edge not found; HTML written, PDF skipped.", file=sys.stderr)
        return 1
    import tempfile
    import time
    profile = tempfile.mkdtemp(prefix="edgepdf_")
    if PDF.exists():
        PDF.unlink()
    cmd = [edge, "--headless=new", "--disable-gpu",
           "--user-data-dir=" + profile, "--no-pdf-header-footer",
           "--print-to-pdf=" + str(PDF), HTML.as_uri()]
    print("running:", " ".join(cmd))
    subprocess.run(cmd, check=False)
    for _ in range(120):
        if PDF.exists():
            break
        time.sleep(0.5)
    ok = PDF.exists()
    if ok:
        time.sleep(1.0)
        print("pdf:", PDF, PDF.stat().st_size, "bytes")
    else:
        print("pdf NOT produced", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
