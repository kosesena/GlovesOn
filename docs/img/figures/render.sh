#!/usr/bin/env bash
# Renders the README figures from their HTML sources with headless Chrome.
# The stills are the film's; ui-*.jpg are unedited crops of the real screen.
set -euo pipefail
cd "$(dirname "$0")"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
for f in confirmed-write-storyboard confirmed-write-gate; do
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --allow-file-access-from-files \
    --window-size=1600,1000 --screenshot="$PWD/$f.png" --virtual-time-budget=4000 "file://$PWD/$f.html" 2>/dev/null
  python3 -c "from PIL import Image; Image.open('$f.png').convert('RGB').save('$f.jpg', quality=88)"
  rm -f "$f.png"; echo "rendered $f.jpg"
done
