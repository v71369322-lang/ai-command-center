#!/bin/bash
# Root operator installs a fixed prepare-only channel, never an unrestricted runner.
set -euo pipefail
umask 077
[ "$(id -u)" = 0 ]
[ "$(hostname -s)" = brain1 ]
[ "$(id -u acc-control)" = 1000 ]
[ "$(id -u acc-exec)" = 1001 ]
id acc-gh-runner >/dev/null
for target in /usr/local/libexec/acc-telegram-prepare-channel.py /usr/local/libexec/acc-telegram-prepare-fixed.sh /etc/systemd/system/acc-telegram-prepare-fixed.service /etc/systemd/system/acc-telegram-prepare-fixed.path /var/lib/acc-telegram-source-handoff /var/lib/acc-telegram-prepare-receipt /home/acc-control/f32; do
  [ ! -e "$target" ] || { echo "Existing target: $target; reconcile instead of overwriting"; exit 1; }
done
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
python3 - "$tmp" <<'PY'
import os,stat,sys
from pathlib import Path
source=Path('/var/lib/acc-gh-runner/bootstrap-telegram')
for name in ['prepare_channel.py','prepare_fixed_release.sh','acc-prepare-fixed.service','acc-prepare-fixed.path','source.json']:
    fd=os.open(source/name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        info=os.fstat(f.fileno())
        assert stat.S_ISREG(info.st_mode) and info.st_size<=8*1024*1024
        raw=f.read(8*1024*1024+1)
        assert len(raw)<=8*1024*1024
    Path(sys.argv[1],name).write_bytes(raw)
PY
( cd "$tmp"; sha256sum -c <<'SUMS'
93dc53e9fc0066f6633bcb58e9c4fdeb2975f5cf90d749ae5a7fed00ec321094  prepare_channel.py
95b58c7c6144448c320f063535aebbd5074b2d89e546b596af599bb1d965c449  prepare_fixed_release.sh
3f43fdafbb391e3e0072951879285d7d86940a3b46bb50cdd7ffa827ed9a7051  acc-prepare-fixed.service
8d78f53970273bb158cf8b22c0ecca2037e843485f50cbafdcc2697dcd2218c3  acc-prepare-fixed.path
SUMS
)
if ! (command -v git && python3.12 -c 'import venv,ensurepip') >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends git python3.12-venv
fi
install -d -m 0755 /usr/local/libexec
install -o root -g root -m 0444 "$tmp/prepare_channel.py" /usr/local/libexec/acc-telegram-prepare-channel.py
install -o root -g root -m 0444 "$tmp/prepare_fixed_release.sh" /usr/local/libexec/acc-telegram-prepare-fixed.sh
install -o root -g root -m 0644 "$tmp/acc-prepare-fixed.service" /etc/systemd/system/acc-telegram-prepare-fixed.service
install -o root -g root -m 0644 "$tmp/acc-prepare-fixed.path" /etc/systemd/system/acc-telegram-prepare-fixed.path
install -d -o acc-control -g acc-control -m 0700 /home/acc-control/f32 /var/lib/acc-telegram-source-handoff
install -o root -g root -m 0444 "$tmp/source.json" /var/lib/acc-telegram-source-handoff/source.json
install -d -o acc-control -g acc-gh-runner -m 2750 /var/lib/acc-telegram-prepare-receipt
systemctl daemon-reload
systemctl start acc-telegram-prepare-fixed.path
systemctl is-active acc-telegram-prepare-fixed.path
touch /var/lib/acc-gh-runner/bootstrap-telegram/operator.ready
echo PREPARE_CHANNEL_READY
