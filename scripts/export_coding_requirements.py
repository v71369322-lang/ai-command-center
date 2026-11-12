"""Derive the sandbox's fixed check tools and their hashes from the reviewed uv lock."""
import argparse
from pathlib import Path
import tomllib

parser = argparse.ArgumentParser()
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
packages = {p['name']: p for p in tomllib.loads(Path('uv.lock').read_text())['package']}
pending, selected = ['pytest', 'ruff'], set()
while pending:
    name = pending.pop()
    if name not in selected:
        selected.add(name)
        pending.extend(d['name'] for d in packages[name].get('dependencies', []))
lines = ['# Generated from uv.lock by scripts/export_coding_requirements.py; check tools only.']
for name in sorted(selected):
    p = packages[name]
    hashes = sorted({item['hash'] for item in [p['sdist'], *p.get('wheels', [])]})
    continuation = ' ' + chr(92) + '\n    '
    lines.append(name + '==' + p['version'] + continuation
                 + continuation.join('--hash=' + h for h in hashes))
content = '\n'.join(lines) + '\n'
path = Path('requirements.coding.lock')
if args.check:
    if path.read_text() != content:
        raise SystemExit('Coding tool dependency drift')
else:
    path.write_text(content, encoding='utf-8', newline='\n')
