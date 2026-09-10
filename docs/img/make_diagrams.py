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

# The product's own palette, not a diagramming default. Tokens are the ones in
# docs/design-system.html; if they move there, they move here. The gateway is the
# dark green of the primary action and of its node on /how-it-works, so a reader
# who has seen either recognises the box without reading it. Orange is reserved
# for the thing in motion — the packets, and the voice wave.
LIGHT = dict(
    name="light",
    node_text="#20241f", sub="#5c6552", wire="#bcae92", label="#5c6552",
    ext_fill="#fffdf7", ext_stroke="#d8cdb6", ext_text="#20241f",
    hub_stroke="#ce5428",
    gw_fill="#244b35", gw_stroke="#1a3728", gw_text="#f7f1e4", gw_sub="#a9c4b3",
    erp_fill="#eef1e6", erp_stroke="#7f8c72", erp_text="#20241f",
    ui_fill="#f4ead6", ui_stroke="#d8cdb6", ui_text="#20241f",
    packet="#ce5428", glow="#ce5428", wave="#ce5428",
)
DARK = dict(
    name="dark",
    node_text="#edf1e8", sub="#a1ada3", wire="#445046", label="#a1ada3",
    ext_fill="#19201c", ext_stroke="#344039", ext_text="#edf1e8",
    hub_stroke="#e96935",
    gw_fill="#1e3a2b", gw_stroke="#b9edc9", gw_text="#edf1e8", gw_sub="#a9c4b3",
    erp_fill="#222c25", erp_stroke="#648e71", erp_text="#edf1e8",
    ui_fill="#19201c", ui_stroke="#344039", ui_text="#edf1e8",
    packet="#b9edc9", glow="#b9edc9", wave="#edba72",
)

FONT = "system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',sans-serif"
MONO = "ui-monospace,'SF Mono',Menlo,Consolas,monospace"


def box(x, y, w, h, fill, stroke, sw=2, rx=14):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def text(x, y, s, fill, size=16, weight="600", anchor="middle", family=FONT, extra=""):
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{extra}>{s}</text>')


def voice_wave(cx, cy, height, colour, bar=2.2, gap=1.5):
    """The five-bar mark from the hero, in SVG, moving the way the CSS moves it.

    `.voice-wave i` scales each bar on Y about its own centre. SMIL has no
    transform-origin, so the same motion is written as a paired y/height
    animation instead. The ratios, the 1.3s period, the ease-in-out and the
    negative delays are the stylesheet's — negative so the bars are already out
    of step in the first frame, rather than starting together and drifting apart.
    """
    ratios = (0.35, 0.65, 0.95, 0.65, 0.35)
    delays = ("0s", "-0.4s", "-0.8s", "-0.2s", "-0.6s")
    ease = "0.42 0 0.58 1;0.42 0 0.58 1"
    span = 5 * bar + 4 * gap
    out = []
    for i, (ratio, delay) in enumerate(zip(ratios, delays, strict=True)):
        x = cx - span / 2 + i * (bar + gap)
        hi = height * ratio / 2          # half-height at full scale
        lo = hi * 0.35
        keys = (f'dur="1.3s" begin="{delay}" repeatCount="indefinite" calcMode="spline" '
                f'keyTimes="0;0.5;1" keySplines="{ease}"')
        out.append(
            f'<rect x="{x:.2f}" y="{cy - lo:.2f}" width="{bar}" height="{lo * 2:.2f}" '
            f'rx="{bar / 2}" fill="{colour}">'
            f'<animate attributeName="y" {keys} '
            f'values="{cy - lo:.2f};{cy - hi:.2f};{cy - lo:.2f}"/>'
            f'<animate attributeName="height" {keys} '
            f'values="{lo * 2:.2f};{hi * 2:.2f};{lo * 2:.2f}"/></rect>')
    return "\n  ".join(out)


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
        # Mono for the wire captions, as on the site, where the small
        # letter-spaced monospace is what marks a machine-to-machine detail.
        out.append(text(lx, ly, label, c["label"], size=11, weight="500",
                        family=MONO, extra=' letter-spacing="0.04em"'))
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

    # the worker — carrying the hero's own mark, because this is the one box
    # where something is actually being said
    p.append(box(24, 258, 160, 76, c["ui_fill"], c["ui_stroke"]))
    p.append(text(97, 290, "Worker", c["ui_text"], 16))
    p.append(voice_wave(139, 285, 17, c["wave"]))
    p.append(text(104, 312, "gloves on, hands full", c["sub"], 12, "500"))

    # AssemblyAI — deliberately the plainest box on the page. It holds nothing.
    p.append(box(240, 50, 260, 110, c["ext_fill"], c["ext_stroke"]))
    p.append(text(370, 84, "AssemblyAI", c["ext_text"], 17))
    p.append(text(370, 106, "Voice Agent API", c["ext_text"], 17))
    p.append(text(370, 132, "STT · turns · LLM · TTS", c["sub"], 13, "500"))
    p.append(text(370, 150, "no URL of ours, no secret", c["sub"], 12, "500"))

    # the browser — the hub, because the tool call lands here. Orange edge: it is
    # the part of this picture that changed.
    p.append(box(240, 240, 260, 112, c["ext_fill"], c["hub_stroke"], sw=2.5))
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
    p.append(text(743, 253, "FastAPI", c["gw_sub"], 13, "500"))
    p.append(text(743, 284, "/api/voice-tools/* · allow-list", c["gw_text"], 13, "500"))
    p.append(text(743, 306, "/erp/* · the shared secret", c["gw_text"], 13, "500"))
    p.append(text(743, 328, "draft protocol · duplicate guard", c["gw_text"], 13, "500"))
    p.append(text(743, 350, "spoken read-back · audit", c["gw_text"], 13, "500"))

    # S/4HANA cylinder. Dashed on purpose, the same way /how-it-works dashes it:
    # everything else in this picture is real code, and this one is a stand-in.
    cx, cy, cw, ch = 922, 66, 154, 116
    p.append(f'<path d="M{cx},{cy+16} a{cw/2},16 0 0,1 {cw},0 v{ch-32} a{cw/2},16 0 0,1 -{cw},0 z" '
             f'fill="{c["erp_fill"]}" stroke="{c["erp_stroke"]}" stroke-width="2" '
             f'stroke-dasharray="7 5"/>')
    p.append(f'<path d="M{cx},{cy+16} a{cw/2},16 0 0,0 {cw},0" fill="none" '
             f'stroke="{c["erp_stroke"]}" stroke-width="2" stroke-dasharray="7 5"/>')
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
