#!/usr/bin/env python3
"""
Builds the README diagrams as SVG, once per colour scheme.

Why a generated SVG and not a Mermaid block: GitHub renders Mermaid inside a
viewer that puts pan, zoom and copy controls over the top-right and bottom-right
corners of the drawing, which covered a node. An <img> has no such overlay. It
also lets the wires carry moving packets — SMIL animation runs inside an image,
scripts do not — so the picture shows direction instead of asserting it.

Run:  python3 docs/img/make_diagrams.py
"""

from pathlib import Path

W, H = 1120, 430
VIEW = "0 34 1120 388"

LIGHT = dict(
    name="light",
    node_text="#0f172a", sub="#475569", wire="#94a3b8", label="#475569",
    ext_fill="#f5f3ff", ext_stroke="#7c3aed", ext_text="#2e1065",
    gw_fill="#dbeafe", gw_stroke="#2563eb", gw_text="#0b1b33",
    erp_fill="#dcfce7", erp_stroke="#16a34a", erp_text="#052e16",
    ui_fill="#f1f5f9", ui_stroke="#64748b", ui_text="#0f172a",
    packet="#2563eb", glow="#2563eb",
)
DARK = dict(
    name="dark",
    node_text="#e2e8f0", sub="#94a3b8", wire="#475569", label="#94a3b8",
    ext_fill="#221049", ext_stroke="#a78bfa", ext_text="#ede9fe",
    gw_fill="#0b2545", gw_stroke="#60a5fa", gw_text="#dbeafe",
    erp_fill="#052e16", erp_stroke="#4ade80", erp_text="#dcfce7",
    ui_fill="#1e293b", ui_stroke="#94a3b8", ui_text="#e2e8f0",
    packet="#60a5fa", glow="#60a5fa",
)

FONT = "system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',sans-serif"


def box(x, y, w, h, fill, stroke, sw=2, rx=14):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def text(x, y, s, fill, size=16, weight="600", anchor="middle"):
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{s}</text>')


def wire(path, c, label=None, lx=0, ly=0, dur="2.6s", delay="0s"):
    """A connector plus the packet that travels along it.

    The circle carries cx/cy of the path's own start: before a delayed
    animateMotion begins, the element sits wherever its geometry says, and a
    circle defaulting to 0,0 parks a stray dot in the corner for the first
    second a reader looks at the drawing.
    """
    sx, sy = path.split()[1].split(",")
    out = [
        f'<path d="{path}" fill="none" stroke="{c["wire"]}" stroke-width="2"/>',
        f'<path d="{path}" fill="none" stroke="{c["packet"]}" stroke-width="2.5" '
        f'stroke-linecap="round" stroke-dasharray="12 48" opacity="0.45">'
        f'<animate attributeName="stroke-dashoffset" from="60" to="0" '
        f'dur="{dur}" begin="{delay}" repeatCount="indefinite"/></path>',
        f'<circle cx="{sx}" cy="{sy}" r="5" fill="{c["packet"]}">'
        f'<animateMotion dur="{dur}" begin="{delay}" repeatCount="indefinite" path="{path}"/>'
        f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.12;0.88;1" '
        f'dur="{dur}" begin="{delay}" repeatCount="indefinite"/></circle>',
    ]
    if label:
        out.append(text(lx, ly, label, c["label"], size=13, weight="500"))
    return "\n  ".join(out)


def build(c):
    p = []
    p.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{VIEW}" '
             f'width="1120" height="388" role="img" '
             f'aria-label="GlovesOn architecture: the worker speaks to the browser, which '
             f'streams audio to the AssemblyAI Voice Agent API; the agent\'s tool call comes '
             f'back down to the browser, which posts it to the GlovesOn gateway with a '
             f'session capability. The gateway holds the shared secret, speaks OData to '
             f'S/4HANA and streams the live warehouse screen back over SSE.">')
    p.append(f'''<defs>
    <marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="{c['wire']}"/>
    </marker>
  </defs>''')

    # wires first, so the boxes sit on top of them.
    #
    # The two vertical wires between the browser and AssemblyAI are the whole
    # point of this drawing. Audio goes up; the agent's tool call comes back
    # DOWN, to the page — there is no wire from AssemblyAI to the gateway,
    # because since ADR-0006 nothing at the provider holds our address or our
    # secret. Drawing one was the error this revision fixes.
    # No caption on the first hop: the gap is 56px and any word sits on a box.
    p.append(wire("M 184,296 L 226,296", c, None, 0, 0, "1.4s", "0s"))
    p.append(wire("M 310,240 L 310,168", c, "audio", 300, 206, "1.6s", "0.1s"))
    p.append(wire("M 430,160 L 430,232", c, "the tool call, back to the page",
                  446, 206, "1.9s", "0.5s"))
    p.append(wire("M 500,296 L 600,296", c, "capability", 557, 284, "1.9s", "0.9s"))
    p.append(wire("M 872,246 L 916,162", c, "OData", 912, 206, "2.1s", "1.2s"))
    p.append(wire("M 872,318 L 916,322", c, "SSE", 898, 306, "2.1s", "1.4s"))
    for d in ("M 184,296 L 234,296", "M 310,240 L 310,160", "M 430,160 L 430,240",
              "M 500,296 L 608,296", "M 872,246 L 922,152", "M 872,318 L 922,323"):
        p.append(f'<path d="{d}" fill="none" stroke="{c["wire"]}" stroke-width="2" marker-end="url(#a)"/>')

    # the worker
    p.append(box(24, 258, 160, 76, c["ui_fill"], c["ui_stroke"]))
    p.append(text(104, 290, "Worker", c["ui_text"], 16))
    p.append(text(104, 312, "gloves on, hands full", c["sub"], 12, "500"))

    # AssemblyAI
    p.append(box(240, 50, 260, 110, c["ext_fill"], c["ext_stroke"]))
    p.append(text(370, 84, "AssemblyAI", c["ext_text"], 17))
    p.append(text(370, 106, "Voice Agent API", c["ext_text"], 17))
    p.append(text(370, 132, "STT · turns · LLM · TTS", c["sub"], 13, "500"))
    p.append(text(370, 150, "no URL of ours, no secret", c["sub"], 12, "500"))

    # the browser — the hub, because the tool call lands here
    p.append(box(240, 240, 260, 112, c["ext_fill"], c["ext_stroke"]))
    p.append(text(370, 274, "Browser", c["ext_text"], 17))
    p.append(text(370, 300, "mic · PCM16 24 kHz", c["sub"], 13, "500"))
    p.append(text(370, 320, "relays the tool call", c["sub"], 13, "500"))
    p.append(text(370, 338, "holds a session capability", c["sub"], 12, "500"))

    # gateway — the emphasised box, with a slow breathing outline
    p.append(f'<rect x="614" y="196" width="258" height="172" rx="16" fill="{c["gw_fill"]}" '
             f'stroke="{c["gw_stroke"]}" stroke-width="3"/>')
    p.append(f'<rect x="614" y="196" width="258" height="172" rx="16" fill="none" '
             f'stroke="{c["glow"]}" stroke-width="3" opacity="0.0">'
             f'<animate attributeName="opacity" values="0;0.55;0" dur="3.4s" repeatCount="indefinite"/>'
             f'<animate attributeName="stroke-width" values="3;9;3" dur="3.4s" repeatCount="indefinite"/></rect>')
    p.append(text(743, 232, "GlovesOn Gateway", c["gw_text"], 17))
    p.append(text(743, 253, "FastAPI", c["sub"], 13, "500"))
    p.append(text(743, 284, "/api/voice-tools/* · allow-list", c["gw_text"], 13, "500"))
    p.append(text(743, 306, "/erp/* · the shared secret", c["gw_text"], 13, "500"))
    p.append(text(743, 328, "draft protocol · duplicate guard", c["gw_text"], 13, "500"))
    p.append(text(743, 350, "spoken read-back · audit", c["gw_text"], 13, "500"))

    # S/4HANA cylinder
    cx, cy, cw, ch = 922, 66, 154, 116
    p.append(f'<path d="M{cx},{cy+16} a{cw/2},16 0 0,1 {cw},0 v{ch-32} a{cw/2},16 0 0,1 -{cw},0 z" '
             f'fill="{c["erp_fill"]}" stroke="{c["erp_stroke"]}" stroke-width="2"/>')
    p.append(f'<path d="M{cx},{cy+16} a{cw/2},16 0 0,0 {cw},0" fill="none" '
             f'stroke="{c["erp_stroke"]}" stroke-width="2"/>')
    p.append(text(cx + cw / 2, cy + 62, "S/4HANA", c["erp_text"], 17))
    p.append(text(cx + cw / 2, cy + 84, "OData + CSRF", c["sub"], 13, "500"))
    p.append(text(cx + cw / 2, cy + 102, "mock today", c["sub"], 12, "500"))

    # live screen
    p.append(box(922, 280, 154, 96, c["ui_fill"], c["ui_stroke"]))
    p.append(text(999, 312, "Live screen", c["ui_text"], 16))
    p.append(text(999, 334, "the material", c["sub"], 12, "500"))
    p.append(text(999, 350, "document, as it posts", c["sub"], 12, "500"))

    # footer note
    p.append(text(W / 2, 408, "the agent never sees SAP, and never sees the gateway either "
                              "— the write is the gateway's alone",
                  c["sub"], 14, "500"))
    p.append("</svg>")
    return "\n  ".join(p) + "\n"


if __name__ == "__main__":
    out = Path(__file__).resolve().parent
    for c in (LIGHT, DARK):
        (out / f"architecture-{c['name']}.svg").write_text(build(c))
        print("wrote", out / f"architecture-{c['name']}.svg")
