#!/bin/bash
# Root-owned service program; never run from a runner-writable checkout.
set -euo pipefail
umask 077
export HOME=/home/acc-control
export PATH=/usr/local/bin:/usr/bin:/bin
unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH
unset PYTHONPATH GIT_CONFIG GIT_CONFIG_COUNT GIT_DIR GIT_WORK_TREE
base=/home/acc-control/f30
receipt=/var/lib/acc-prepare-receipt/status
mkdir -p "$base"
chmod 700 "$base"
exec 9>"$base/prepare.lock"
flock -n 9 || exit 1
if [ -e "$base/attempted" ]; then
  echo 'Reconciliation required: previous attempt exists' >"$receipt"
  exit 1
fi
touch "$base/attempted"
echo PREPARING >"$receipt"
chmod 640 "$receipt"
trap 'echo FAILED_REQUIRES_OPERATOR_REVIEW >"$receipt"' ERR
exec >>"$base/prepare.log" 2>&1
[ "$(id -u)" = 1000 ]
[ "$(df --output=avail -B1 "$base" | tail -1)" -ge 26843545600 ]
for program in git python3.12 docker flock; do command -v "$program"; done
for uid in 1000 1001; do
  docker --host="unix:///run/user/$uid/docker.sock" info --format '{{json .}}' |
    python3.12 -c 'import json,sys;s=json.load(sys.stdin);assert any("rootless" in v for v in s["SecurityOptions"]);assert s["CgroupVersion"]=="2";assert all(s.get(k) for k in ("MemoryLimit","PidsLimit","CpuCfsQuota"))'
done
python3.12 /usr/local/libexec/acc-prepare-channel.py hydrate \
  /var/lib/acc-source-handoff/source.json "$base/source"
cd "$base/source"
test "$(git rev-parse HEAD)" = 53565cc2ca232fb2cf6d6552a3ae04b462d92956
python3.12 -m venv "$base/tools"
"$base/tools/bin/python" -m pip install --require-hashes --only-binary=:all: --no-deps -r requirements.lock
ACC_CONTROL_UID=1000 ACC_EXECUTION_UID=1001 sh infra/vps/build_release.sh
export PYTHONPATH="$base/source/src"
"$base/tools/bin/python" -m command_center.deployment init-state --data-root "$base/state"
"$base/tools/bin/python" -m command_center.deployment prepare --source "$base/source" \
  --bundle "$base/bundle" --control-uid 1000 --execution-uid 1001 --data-root "$base/state"
"$base/tools/bin/python" -m command_center.deployment inspect --bundle "$base/bundle" >"$receipt"
chmod 640 "$receipt"
# No install, task admission, owner authentication or external API activation.
