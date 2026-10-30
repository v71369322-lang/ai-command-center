"""Locked all-dependency audit plus explicit, retained static-analysis triage."""
import json
import os
from pathlib import Path
import subprocess
import sys


def run(args, *, expected=(0,)):
    result = subprocess.run(args, capture_output=True, timeout=180)
    if result.returncode not in expected:
        # Error output may include configuration; publish a stable code only.
        raise RuntimeError('security_check_failed:' + Path(args[0]).name)
    return result


def main():
    target = Path('.runtime')
    target.mkdir(exist_ok=True)
    for name in ('all-pip-audit.json', 'bandit.json', 'security-summary.json'):
        (target / name).unlink(missing_ok=True)
    if os.environ.get('F1_BUILD_CA_FILE'):
        os.environ.setdefault('REQUESTS_CA_BUNDLE', os.environ['F1_BUILD_CA_FILE'])
    run(['uv', 'export', '--frozen', '--no-emit-project', '--format', 'requirements-txt',
         '--output-file', str(target / 'all-requirements.txt')])
    run([sys.executable, '-m', 'pip_audit', '--cache-dir', str(target / 'pip-audit-cache'),
         '--no-deps', '--disable-pip', '-r', str(target / 'all-requirements.txt'),
         '--format', 'json', '--output', str(target / 'all-pip-audit.json')])
    npm = run(['npm', 'audit', '--prefix', 'web', '--cache', str(target / 'npm-cache'), '--json'])
    (target / 'npm-audit.json').write_bytes(npm.stdout)
    run([sys.executable, '-m', 'bandit', '-r', 'src', 'scripts', 'infra/vps/operations',
         'infra/vps/stage_telegram_update.py', 'infra/vps/prepare_github_token.py',
         'infra/vps/inspect_first_recovery.py', '-f', 'json',
         '-o', str(target / 'bandit.json')], expected=(0, 1))
    static = json.loads((target / 'bandit.json').read_text())
    # Keep every finding. These LOW rules were manually reviewed in
    # SECURITY_REVIEW.md; a new rule or MEDIUM/HIGH blocks final verification.
    reviewed_low_rules = {'B404', 'B603', 'B607', 'B110', 'B105'}
    unexpected = [f for f in static.get('results', [])
                  if f['issue_severity'] != 'LOW' or f['test_id'] not in reviewed_low_rules]
    if static.get('errors') or unexpected:
        # Only locations/rule names, never issue text or source that could contain a credential.
        print(json.dumps([{'file': f['filename'], 'line': f['line_number'],
                           'rule': f['test_id'], 'severity': f['issue_severity']} for f in unexpected]))
        raise RuntimeError('unreviewed_static_security_finding')
    audit = json.loads((target / 'all-pip-audit.json').read_text())
    revision = os.environ.get('F1_SOURCE_REVISION') or run(['git', 'rev-parse', 'HEAD']).stdout.decode().strip()
    summary = {'revision': revision, 'python_dependencies': len(audit['dependencies']),
               'python_advisories': sum(len(d.get('vulns', [])) for d in audit['dependencies']),
               'npm_advisories': json.loads(npm.stdout)['metadata']['vulnerabilities']['total'],
               'bandit_medium_high': 0, 'bandit_reviewed_low': len(static.get('results', []))}
    (target / 'security-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('Locked dependency audit and static security gates: PASS')
    print(json.dumps(summary, sort_keys=True))


if __name__ == '__main__':
    main()
