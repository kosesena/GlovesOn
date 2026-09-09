"""Run offline voice contracts without a paid service or a database reset."""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
node = shutil.which('node')
if not node:
    raise SystemExit('Node.js is required for browser transport checks.')
for script in ('voice_pause.cjs', 'voice_policy.cjs', 'voice_lifecycle.cjs'):
    subprocess.run([node, str(ROOT/'checks'/script)], cwd=ROOT, check=True)
subprocess.run([sys.executable, '-m', 'pytest', 'checks', '-q'], cwd=ROOT, check=True)
print('Offline contracts passed. This does not measure microphone recognition or warehouse noise.')
