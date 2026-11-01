#!/bin/bash
# Owner-approved build preparation only. No deployment, token issuance or AI.
set -euo pipefail
set +x
umask 077
export PATH=/usr/local/bin:/usr/bin:/bin
application=bf91c05c754ad41e7f89223ec8d05c02c9007de1
base=/home/acc-control/first-experiment-recovery-release
check_window() {
  python3 -I - <<'PY'
import os, time
value = os.environ.get('ACC_BUILD_APPROVED_UNTIL', '')
now = int(time.time())
if not value.isdigit() or not now < int(value) <= now + 7200:
    raise SystemExit('BUILD_APPROVAL_MISSING_OR_EXPIRED')
PY
}
check_window
python3 -I - <<'PY_OPERATOR'
import os, re
if not re.fullmatch('[a-f0-9]{40}', os.environ.get('ACC_OPERATOR_REVISION', '')):
    raise SystemExit('EXACT_OPERATOR_REVISION_REQUIRED')
PY_OPERATOR
operator=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
[ "$(git --no-replace-objects -C "$operator" rev-parse HEAD)" = "$ACC_OPERATOR_REVISION" ]
[ -z "$(git -C "$operator" status --porcelain)" ]
[ "$(id -u)" = 1000 ]
[ "$(hostname -s)" = brain1 ]
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH
unset GIT_DIR GIT_WORK_TREE GIT_CONFIG GIT_CONFIG_COUNT PYTHONPATH
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0
export GIT_ALLOW_PROTOCOL=ssh
for program in git ssh python3 docker timeout; do command -v "$program" >/dev/null; done
python3 -I - <<'PY'
import json, shutil, stat
from pathlib import Path
base = Path('/home/acc-control/first-experiment-recovery-release')
if base.exists() or base.is_symlink():
    raise SystemExit('INSPECT_EXISTING_BUILD_WORKSPACE_NO_RETRY')
d = json.loads(Path('/home/acc-control/f30/state/deployment.json').read_text())
expected = {'phase': 'VERIFIED',
    'revision': '322186dc180257c618d8b159c78faa6e5bbf0b43',
    'bundle': 'ac6462b47f69a3cbc967ac2c9dd62064d6b3dc7813503d34782e1dd1830d094d',
    'directory': '/home/acc-control/first-experiment-github-capability-release/integration-preparation/candidate'}
if any(d.get(key) != value for key, value in expected.items()):
    raise SystemExit('VERIFIED_PREDECESSOR_CHANGED')
if shutil.disk_usage('/home/acc-control').free < 25 * 2**30:
    raise SystemExit('BUILD_DISK_LOW')
for name in ('id_ed25519', 'github_known_hosts'):
    p = Path('/home/acc-control/f34-source-access') / name
    info = p.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 1000 or info.st_nlink != 1:
        raise SystemExit('SOURCE_ACCESS_CUSTODY_CHANGED')
    mode = stat.S_IMODE(info.st_mode)
    if mode & 0o022 or (name == 'id_ed25519' and mode != 0o600):
        raise SystemExit('SOURCE_ACCESS_CUSTODY_CHANGED')
PY
for uid in 1000 1001; do
  docker --host="unix:///run/user/$uid/docker.sock" info --format '{{json .SecurityOptions}}' |
    python3 -I -c 'import json,sys;assert any("rootless" in v for v in json.load(sys.stdin))'
done
check_window
mkdir -m 700 "$base"
set -o noclobber
exec > "$base/build.log" 2>&1
export GIT_SSH_COMMAND='/usr/bin/ssh -F /dev/null -i /home/acc-control/f34-source-access/id_ed25519 -o IdentityAgent=none -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ssh-ed25519 -o GlobalKnownHostsFile=/dev/null -o UserKnownHostsFile=/home/acc-control/f34-source-access/github_known_hosts -o ConnectTimeout=15'
mkdir -m 700 "$base/source"
git -C "$base/source" init --quiet --template=
git -C "$base/source" remote add origin git@github.com:v71369322-lang/ai-command-center.git
timeout 120s git -C "$base/source" fetch --depth=1 origin "$application"
git -C "$base/source" -c core.hooksPath=/dev/null checkout --detach "$application"
[ "$(git --no-replace-objects -C "$base/source" rev-parse HEAD)" = "$application" ]
[ -z "$(git -C "$base/source" status --porcelain)" ]
cd "$base/source"
# Existing tools Python can be reused only while its locked runtime is identical.
cmp requirements.lock /home/acc-control/first-experiment-github-capability-release/source/requirements.lock
check_window
ACC_CONTROL_UID=1000 ACC_EXECUTION_UID=1001 sh infra/vps/build_release.sh
echo FIRST_EXPERIMENT_RECOVERY_IMAGES_BUILT_NOT_DEPLOYED
