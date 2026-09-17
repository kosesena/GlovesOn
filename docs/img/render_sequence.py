#!/usr/bin/env python3
"""
Renders confirmed-write.mmd to SVG, once per colour scheme, in the product's palette.

Why a script and not two mermaid-cli commands in a comment: doing it by hand needed
three fiddly steps every time, and the third was always forgotten. mermaid-cli emits
`width="100%"`, which an <img> cannot size itself from, so the committed files carry
explicit pixel dimensions taken from the viewBox. And the palette has to be injected
per scheme, on a copy of the source, because a `%%{init}%%` block written into the
.mmd itself would force one palette on both.

Colours are the tokens in docs/design-system.html. If they move there, move them here.

Run:  python3 docs/img/render_sequence.py     (needs node; mermaid-cli comes via npx)
"""

import json
import re
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "confirmed-write.mmd"

# Unquoted on purpose: this string is interpolated into a JSON directive and then into
# CSS, and a nested quote survives neither trip.
FONT = "system-ui, -apple-system, Segoe UI, Roboto, Helvetica Neue, sans-serif"

# The note is the one orange thing, because it carries the sentence this whole
# diagram exists to make: at that moment there is no write tool.
LIGHT = {
    "fontFamily": FONT, "fontSize": "15px",
    "primaryColor": "#fffdf7", "primaryTextColor": "#20241f",
    "primaryBorderColor": "#d8cdb6", "lineColor": "#bcae92", "textColor": "#20241f",
    "actorBkg": "#fffdf7", "actorBorder": "#c9bb9e", "actorTextColor": "#20241f",
    "actorLineColor": "#cdbfa2",
    "signalColor": "#9a917c", "signalTextColor": "#20241f",
    "noteBkgColor": "#fdeee2", "noteBorderColor": "#ce5428", "noteTextColor": "#20241f",
    "labelBoxBkgColor": "#244b35", "labelBoxBorderColor": "#244b35",
    "labelTextColor": "#f7f1e4",
    "activationBkgColor": "#f4ead6", "activationBorderColor": "#ce5428",
    "sequenceNumberColor": "#f7f1e4",
}
DARK = {
    "fontFamily": FONT, "fontSize": "15px",
    "primaryColor": "#19201c", "primaryTextColor": "#edf1e8",
    "primaryBorderColor": "#344039", "lineColor": "#445046", "textColor": "#edf1e8",
    "actorBkg": "#222c25", "actorBorder": "#4a5a4f", "actorTextColor": "#edf1e8",
    "actorLineColor": "#3d4a41",
    "signalColor": "#8d9a90", "signalTextColor": "#edf1e8",
    "noteBkgColor": "#2c2620", "noteBorderColor": "#e96935", "noteTextColor": "#edf1e8",
    "labelBoxBkgColor": "#1e3a2b", "labelBoxBorderColor": "#b9edc9",
    "labelTextColor": "#edf1e8",
    "activationBkgColor": "#222c25", "activationBorderColor": "#e96935",
    "sequenceNumberColor": "#151b18",
}


# The film's palette, with its own painted background so the README can show one
# drawing on GitHub's light and dark pages alike. Orange is the note and the
# activations, as before; mint is the gateway's label box, as on the deck.
CINE = {
    "fontFamily": FONT, "fontSize": "15px",
    "primaryColor": "#141b17", "primaryTextColor": "#f3f1ea",
    "primaryBorderColor": "#3a463d", "lineColor": "#5d675f", "textColor": "#f3f1ea",
    "actorBkg": "#1a221d", "actorBorder": "#4a5a4f", "actorTextColor": "#f3f1ea",
    "actorLineColor": "#3d4a41",
    "signalColor": "#9aa69d", "signalTextColor": "#f3f1ea",
    "noteBkgColor": "#2a221b", "noteBorderColor": "#f08a45", "noteTextColor": "#f3f1ea",
    "labelBoxBkgColor": "#1e3a2b", "labelBoxBorderColor": "#b9edc9",
    "labelTextColor": "#f3f1ea",
    "activationBkgColor": "#1a221d", "activationBorderColor": "#f08a45",
    "sequenceNumberColor": "#0e1310",
}
BACKGROUND = {"light": "transparent", "dark": "transparent", "cinematic": "#0e1310"}


def render(name: str, variables: dict, tmp: Path) -> None:
    # The palette goes in as an %%{init}%% directive on a copy of the source, not
    # through mermaid-cli's -c config file. The config file is silently ignored for
    # sequence theming — the first attempt at this rendered in mermaid's defaults and
    # looked like it had worked. The directive is honoured; the copy is so that
    # confirmed-write.mmd stays a diagram rather than a diagram plus one theme.
    # fontFamily has to sit at the config root as well: mermaid builds the stylesheet
    # from the root value, and the themeVariables copy alone leaves the drawing in
    # Trebuchet.
    config = {"theme": "base", "fontFamily": FONT, "themeVariables": variables}
    directive = "%%{init: " + json.dumps(config) + "}%%\n"
    themed = tmp / f"{name}.mmd"
    themed.write_text(directive + SOURCE.read_text())
    raw = tmp / f"{name}.svg"
    subprocess.run(
        ["npx", "-y", "@mermaid-js/mermaid-cli@11", "-i", str(themed),
         "-o", str(raw), "-b", BACKGROUND[name]],
        check=True,
    )
    svg = raw.read_text()
    box = re.search(r'viewBox="(-?[\d.]+) (-?[\d.]+) ([\d.]+) ([\d.]+)"', svg)
    width, height = float(box.group(3)), float(box.group(4))
    # Only the width is touched. The id stays `my-svg` because every rule in the
    # stylesheet mermaid embeds is scoped `#my-svg .actor{...}` — renaming it, which
    # an earlier version of this script did for tidiness, silently unstyles the whole
    # drawing and the palette work looks like it simply did not apply.
    svg = svg.replace('width="100%"', f'width="{width:g}" height="{height:g}"', 1)
    out = HERE / f"confirmed-write-{name}.svg"
    out.write_text(svg)
    print(f"wrote {out}  {width:g}x{height:g}")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = Path(raw_tmp)
        render("light", LIGHT, tmp)
        render("dark", DARK, tmp)
        render("cinematic", CINE, tmp)
