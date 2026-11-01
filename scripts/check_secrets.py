"""Check tracked files against current local synthetic credentials; print paths only."""
import json
from pathlib import Path
import subprocess

root = Path('.runtime/secrets')
known = []
for path in root.glob('*'):
    content = path.read_text().strip()
    if path.suffix == '.json':
        known.extend(json.loads(content).values())
    else:
        known.append(content)
tracked = subprocess.check_output(['git','ls-files','-z']).split(b'\0')
failures = []
for raw in tracked:
    if not raw:
        continue
    path = Path(raw.decode())
    if not path.is_file():
        continue
    content = path.read_bytes()
    if any(value and value.encode() in content for value in known):
        failures.append(str(path))
if failures:
    raise SystemExit('Credential found in tracked path(s): ' + ', '.join(failures))
print('No current runtime credential values in tracked files; this is not a universal secret detector.')
