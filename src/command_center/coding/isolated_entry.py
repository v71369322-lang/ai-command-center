"""Untrusted offline patch/check process. Called only inside the F1 sandbox."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

from ..isolated_coding import report, validate_payload


def execute(value, root):
    files, _ = validate_payload(value)
    root = Path(root)
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    for path, source in {**files, **value['replacements']}.items():
        target = root / path
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.write_text(source, encoding='utf-8')
    scope = value['specification']['scope']
    commands = value['specification']['verification_commands']
    checks = []
    deadline = time.monotonic() + scope['max_seconds']
    environment = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(root),
                   'PYTHONPATH': str(root / 'src'), 'PYTHONDONTWRITEBYTECODE': '1',
                   'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'RUFF_NO_CACHE': '1'}
    # No repository configuration/hooks/plugins are imported from outside the slice.
    for argv in commands:
        if argv[0] == 'ruff':
            argv = [str(Path(sys.executable).with_name('ruff')), 'check', '--isolated', '--no-cache', *argv[2:]]
        else:
            argv = [sys.executable, '-m', 'pytest', '-p', 'no:cacheprovider', '-c', '/dev/null', *argv[3:]]
        with tempfile.TemporaryFile(dir=root) as output:
            process = subprocess.Popen(argv, cwd=root, env=environment, stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=output, start_new_session=True)
            try:
                code = process.wait(timeout=max(.001, deadline - time.monotonic()))
            finally:
                # Kill the complete check process group, including background children.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
        checks.append({'command': commands[len(checks)], 'passed': code == 0})
    # Re-read files after untrusted tests; tests cannot smuggle a different artifact.
    for path, source in {**files, **value['replacements']}.items():
        target = root / path
        if (any(p.is_symlink() for p in [target, *target.parents] if p != root.parent)
                or target.read_bytes() != source.encode()):
            raise ValueError('workspace_changed_during_checks')
    expected = set(files)
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() or p.is_symlink()}
    if actual != expected:
        raise ValueError('unexpected_workspace_files')
    return {**report(value), 'checks': checks, 'passed': all(c['passed'] for c in checks)}
