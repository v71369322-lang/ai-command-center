"""Export API schema without runtime credentials or a database connection."""
import argparse
import json
from pathlib import Path
import subprocess

from command_center.api import create_app
from command_center.config import Settings

parser = argparse.ArgumentParser()
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
revision = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
settings = Settings('postgresql+psycopg://schema-only', 'redis://127.0.0.1:6379/0',
                    'public-schema-fixture', {}, revision)
schema = create_app(settings).openapi()
content = json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
path = Path('contracts/openapi.json')
if args.check:
    if path.read_text(encoding='utf-8') != content:
        raise SystemExit('Contract drift: export and review compatibility/version before committing')
else:
    path.write_text(content, encoding='utf-8', newline='\n')
