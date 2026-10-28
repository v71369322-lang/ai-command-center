#!/bin/bash
# Root-owned service program; never run from a runner-writable checkout.
set -euo pipefail
umask 077
export HOME=/home/acc-control
export PATH=/usr/local/bin:/usr/bin:/bin
unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH
unset PYTHONPATH GIT_CONFIG GIT_CONFIG_COUNT GIT_DIR GIT_WORK_TREE
base=/home/acc-control/f32
receipt=/var/lib/acc-telegram-prepare-receipt/status
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
python3.12 -c 'import json;p=json.load(open("/home/acc-control/f30/state/deployment.json"));assert p["phase"]=="VERIFIED";assert p["revision"]=="4cc6ec46bf461d65958f013bb23ac2234b9a7fd3";assert p["bundle"]=="1e151b2953b6debb4bb05096fba20aa6c740665015f31479a50fd25c6ef80106"'
for uid in 1000 1001; do
  docker --host="unix:///run/user/$uid/docker.sock" info --format '{{json .}}' |
    python3.12 -c 'import json,sys;s=json.load(sys.stdin);assert any("rootless" in v for v in s["SecurityOptions"]);assert s["CgroupVersion"]=="2";assert all(s.get(k) for k in ("MemoryLimit","PidsLimit","CpuCfsQuota"))'
done
python3.12 /usr/local/libexec/acc-telegram-prepare-channel.py hydrate \
  /var/lib/acc-telegram-source-handoff/source.json "$base/source"
cd "$base/source"
test "$(git rev-parse HEAD)" = 59d12601ea28475264a18e44c6f1ead0ff5e548f
test "$(git -C /home/acc-control/f31/source rev-parse HEAD)" = 4cc6ec46bf461d65958f013bb23ac2234b9a7fd3
test -z "$(git -C /home/acc-control/f31/source status --porcelain)"
cmp requirements.lock /home/acc-control/f31/source/requirements.lock
tools=/home/acc-control/f30/tools
test -x "$tools/bin/python"
ACC_CONTROL_UID=1000 ACC_EXECUTION_UID=1001 sh infra/vps/build_release.sh
export PYTHONPATH="$base/source/src"
test -f /home/acc-control/f30/state/deployment.json
"$tools/bin/python" -m command_center.deployment prepare --source "$base/source" \
  --bundle "$base/bundle" --control-uid 1000 --execution-uid 1001 --data-root /home/acc-control/f30/state \
  --owner-password-origin http://127.0.0.1:18000 --password-loopback-http
"$tools/bin/python" -m command_center.deployment inspect --bundle "$base/bundle" >"$receipt"
chmod 640 "$receipt"
# No install, task admission, owner authentication or external API activation.
