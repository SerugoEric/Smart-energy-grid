"""Read live layout geometry from a Chrome/Edge page via the DevTools protocol.

Usage: python report\\shots\\cdp_geom.py [port] [expression-file]
"""
import json
import sys
import time
import urllib.request

import websocket

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9333

JS = r"""
(function () {
  const out = {};
  out.dpr = window.devicePixelRatio;
  out.inner = [window.innerWidth, window.innerHeight];
  out.scroll = [window.scrollX, window.scrollY];
  out.doc = [document.documentElement.scrollWidth,
             document.documentElement.scrollHeight];
  const ids = ["g1", "g2", "g3", "g4", "g5", "timings", "geomdbg"];
  for (const id of ids) {
    const el = document.getElementById(id);
    if (!el) { out[id] = null; continue; }
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    out[id] = {x: Math.round(r.x), y: Math.round(r.y + window.scrollY),
               w: Math.round(r.width), h: Math.round(r.height),
               cssH: cs.height, cssW: cs.width, disp: cs.display};
  }
  const h1 = document.querySelector("h1");
  if (h1) { const r = h1.getBoundingClientRect();
            out.h1 = {y: Math.round(r.y + window.scrollY), h: Math.round(r.height)}; }
  const flex = out.g1 ? document.getElementById("g1").parentElement : null;
  if (flex) { const r = flex.getBoundingClientRect();
              out.flex = {x: Math.round(r.x), y: Math.round(r.y + window.scrollY),
                          w: Math.round(r.width), h: Math.round(r.height),
                          cssH: getComputedStyle(flex).height,
                          alignItems: getComputedStyle(flex).alignItems}; }
  const plot = out.g1 ? document.getElementById("g1").querySelector(".js-plotly-plot") : null;
  if (plot) { const r = plot.getBoundingClientRect();
              out.plot = {y: Math.round(r.y + window.scrollY),
                          h: Math.round(r.height), cssH: getComputedStyle(plot).height}; }
  return out;
})()
"""


def http(path):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}") as r:
        return json.load(r)


def main():
    deadline = time.time() + 30
    page = None
    while time.time() < deadline and page is None:
        try:
            targets = http("/json/list")
            pages = [t for t in targets if t.get("type") == "page"
                     and t.get("webSocketDebuggerUrl")]
            page = next((t for t in pages if "8050" in t.get("url", "")),
                        None) or (pages[0] if pages else None)
        except Exception:
            time.sleep(0.5)
    if page is None:
        print("NO PAGE TARGET")
        return
    print(f"# target {page.get('url')}")
    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=60)
    counter = [0]

    def send(method, params=None):
        counter[0] += 1
        ws.send(json.dumps({"id": counter[0], "method": method,
                            "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == counter[0]:
                return msg

    res = send("Runtime.evaluate",
               {"expression": sys.argv[2] if len(sys.argv) > 2 else JS,
                "returnByValue": True, "awaitPromise": True})
    value = res.get("result", {}).get("result", {}).get("value")
    print(json.dumps(value, indent=1))
    ws.close()


if __name__ == "__main__":
    main()
