#!/bin/bash
# Root operator installs a fixed prepare-only channel, never an unrestricted runner.
set -euo pipefail
umask 077
[ "$(id -u)" = 0 ]
[ "$(hostname -s)" = brain1 ]
[ "$(id -u acc-control)" = 1000 ]
[ "$(id -u acc-exec)" = 1001 ]
id acc-gh-runner >/dev/null
for target in /usr/local/libexec/acc-prepare-channel.py /usr/local/libexec/acc-prepare-fixed.sh /etc/systemd/system/acc-prepare-fixed.service /etc/systemd/system/acc-prepare-fixed.path /var/lib/acc-source-handoff /var/lib/acc-prepare-receipt /home/acc-control/f30; do
  [ ! -e "$target" ] || { echo "Existing target: $target; reconcile instead of overwriting"; exit 1; }
done
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
python3 - "$tmp" <<'PY'
import os,stat,sys
from pathlib import Path
source=Path('/var/lib/acc-gh-runner/bootstrap')
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
2fa3c3b294b6cfbe526083639244a04bd03fb3e0588d2faa91710e8775ccc6cd  prepare_channel.py
67c964f368a289970c5ea7b79981bb1c12a1781f959e9445341affc99fa88776  prepare_fixed_release.sh
4359449eb1da601cd12ad0fa504275de37fdef318f2a1a42107e6ec84bad5c96  acc-prepare-fixed.service
30dc63c2c910b88806eb82eef4de25843d919cc945b5ac17db3a3c2f83dfc788  acc-prepare-fixed.path
SUMS
)
if ! (command -v git && python3.12 -c 'import venv,ensurepip') >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends git python3.12-venv
fi
install -d -m 0755 /usr/local/libexec
install -o root -g root -m 0444 "$tmp/prepare_channel.py" /usr/local/libexec/acc-prepare-channel.py
install -o root -g root -m 0444 "$tmp/prepare_fixed_release.sh" /usr/local/libexec/acc-prepare-fixed.sh
install -o root -g root -m 0644 "$tmp/acc-prepare-fixed.service" /etc/systemd/system/acc-prepare-fixed.service
install -o root -g root -m 0644 "$tmp/acc-prepare-fixed.path" /etc/systemd/system/acc-prepare-fixed.path
install -d -o acc-control -g acc-control -m 0700 /home/acc-control/f30 /var/lib/acc-source-handoff
install -o root -g root -m 0444 "$tmp/source.json" /var/lib/acc-source-handoff/source.json
install -d -o acc-control -g acc-gh-runner -m 2750 /var/lib/acc-prepare-receipt
systemctl daemon-reload
systemctl start acc-prepare-fixed.path
systemctl is-active acc-prepare-fixed.path
touch /var/lib/acc-gh-runner/bootstrap/operator.ready
echo PREPARE_CHANNEL_READY
