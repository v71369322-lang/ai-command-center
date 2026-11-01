#!/bin/bash
# Run ONLY after fresh owner source/build approval. Never activate or resume.
set -euo pipefail
set +x
umask 077
export PATH=/usr/local/bin:/usr/bin:/bin
python3 -I - <<'PY_APPROVAL'
import os, re, time
now = int(time.time())
value = os.environ.get('ACC_PREPARE_APPROVED_UNTIL', '')
if not value.isdigit() or not now < int(value) <= now + 7200:
    raise SystemExit('PREPARATION_APPROVAL_MISSING_OR_EXPIRED')
if not re.fullmatch('[a-f0-9]{40}', os.environ.get('ACC_OPERATOR_REVISION', '')):
    raise SystemExit('EXACT_OPERATOR_REVISION_REQUIRED')
if os.environ.get('ACC_TELEGRAM_RELEASE', 'telegram-resume') not in ('telegram-resume', 'telegram-mobile'):
    raise SystemExit('EXACT_TELEGRAM_RELEASE_REQUIRED')
PY_APPROVAL
release=${ACC_TELEGRAM_RELEASE:-telegram-resume}
case "$release" in
  telegram-resume)
    application=bdc8cbcdcf3fe2377fa6cc08250c331d35f99f82
    base=/home/acc-control/telegram-resume-release
    marker=TELEGRAM_RESUME_CANDIDATE_PREPARED_NOT_APPLIED
    ;;
  telegram-mobile)
    application=d932baafce53c0748396abfc019cf81b931ebfec
    base=/home/acc-control/telegram-mobile-release
    marker=TELEGRAM_MOBILE_CANDIDATE_PREPARED_NOT_APPLIED
    ;;
esac
if [ "$(id -u)" != 1000 ] || [ "$(hostname -s)" != brain1 ]; then
  echo DEDICATED_CONTROL_HOST_REQUIRED >&2
  exit 1
fi
export HOME=/home/acc-control
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH
unset GIT_DIR GIT_WORK_TREE GIT_CONFIG GIT_CONFIG_COUNT PYTHONPATH
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0
export GIT_ALLOW_PROTOCOL=ssh
operator=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
[ "$(git --no-replace-objects -C "$operator" rev-parse HEAD)" = "$ACC_OPERATOR_REVISION" ]
[ -z "$(git -C "$operator" status --porcelain)" ]
python3 -I - <<'PY_BASELINE'
import json
from pathlib import Path
p = json.loads(Path('/home/acc-control/f30/state/deployment.json').read_text())
if (p.get('phase') != 'VERIFIED'
    or p.get('revision') != 'b2e71fe073f3109e639dac43496884905ce86d9f'
    or p.get('bundle') != 'a1cf9b0d783cc15a17e8d119167008a81584a051bcd55a0e9b359c519d8be9c8'
    or p.get('directory') != '/home/acc-control/f34/candidate'):
    raise SystemExit('VERIFIED_PREDECESSOR_CHANGED')
PY_BASELINE
[ ! -e "$base" ] && [ ! -L "$base" ]
for program in git ssh python3 docker flock timeout; do command -v "$program" >/dev/null; done
[ "$(df --output=avail -B1 /home/acc-control | tail -1)" -ge 26843545600 ]
[ -f /home/acc-control/f34-source-access/id_ed25519 ]
[ -f /home/acc-control/f34-source-access/github_known_hosts ]
mkdir -m 700 "$base"
exec 9>"$base/prepare.lock"
flock -n 9
exec >>"$base/prepare.log" 2>&1
export GIT_SSH_COMMAND='/usr/bin/ssh -F /dev/null -i /home/acc-control/f34-source-access/id_ed25519 -o IdentityAgent=none -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ssh-ed25519 -o GlobalKnownHostsFile=/dev/null -o UserKnownHostsFile=/home/acc-control/f34-source-access/github_known_hosts -o ConnectTimeout=15'
check_approval() {
  python3 -I - <<'PY_WINDOW'
import os,time
now=int(time.time())
if not now < int(os.environ['ACC_PREPARE_APPROVED_UNTIL']) <= now+7200:
    raise SystemExit('PREPARATION_APPROVAL_EXPIRED')
PY_WINDOW
}
check_approval
mkdir -m 700 "$base/source"
git -C "$base/source" init --quiet --template=
git -C "$base/source" remote add origin git@github.com:v71369322-lang/ai-command-center.git
timeout 120s git -C "$base/source" fetch --depth=1 origin "$application"
git -C "$base/source" -c core.hooksPath=/dev/null checkout --detach "$application"
[ "$(git --no-replace-objects -C "$base/source" rev-parse HEAD)" = "$application" ]
[ -z "$(git -C "$base/source" status --porcelain)" ]
cd "$base/source"
cmp requirements.lock /home/acc-control/f34/source/requirements.lock
check_approval
ACC_CONTROL_UID=1000 ACC_EXECUTION_UID=1001 sh infra/vps/build_release.sh
export PYTHONPATH="$base/source/src"
tools=/home/acc-control/f30/tools/bin/python
check_approval
"$tools" -m command_center.deployment prepare --source "$base/source" \
  --bundle "$base/disabled-bundle" --control-uid 1000 --execution-uid 1001 \
  --data-root /home/acc-control/f30/state \
  --owner-password-origin http://127.0.0.1:18000 --password-loopback-http
check_approval
"$tools" "$operator/infra/vps/stage_telegram_update.py" stage --release "$release" \
  --active-bundle /home/acc-control/f34/candidate \
  --disabled-bundle "$base/disabled-bundle" --output "$base/candidate" \
  --approved-previous a1cf9b0d783cc15a17e8d119167008a81584a051bcd55a0e9b359c519d8be9c8
echo "$marker"
