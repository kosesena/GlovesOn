#!/usr/bin/env bash
# Renders the evidence cards (cream and cinematic) with today's real counts.
# Counts come from git and pytest, never from a hand edit; run this on submission day.
set -euo pipefail
cd "$(dirname "$0")/.."
COMMITS=$(git rev-list --count HEAD)
TESTS=$(.venv/bin/python -m pytest --collect-only -q tests checks 2>&1 | grep -E "^(tests|checks)/.*: [0-9]+$" | awk -F': ' '{s+=$2} END{print s}')
RECEIPTS=$(ls receipts/[0-9]*.json | wc -l | tr -d ' ')
echo "commits=$COMMITS tests=$TESTS receipts=$RECEIPTS"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# The cream card is laid out in 1920x1080 CSS pixels; the cinematic one in 13.333in x 7.5in (1280x720 CSS px at 96 dpi), so it is scaled 1.5x.
for triple in "evidence-card.html:evidence-card-16x9.png:1920,1080:1" "evidence-card-cinematic.html:evidence-card-cinematic-16x9.png:1280,720:1.5"; do
  IFS=: read -r srcname outname win scale <<< "$triple"
  src="submission/$srcname"; out="submission/$outname"; tmp="submission/.render-$$.html"
  sed -e "s/{{COMMITS}}/$COMMITS/g" -e "s/{{TESTS}}/$TESTS/g" -e "s/{{RECEIPTS}}/$RECEIPTS/g" "$src" > "$tmp"
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size="$win" --force-device-scale-factor="$scale" \
    --screenshot="$PWD/$out" --virtual-time-budget=5000 "file://$PWD/$tmp" 2>/dev/null
  rm -f "$tmp"; echo "rendered $out"
done
