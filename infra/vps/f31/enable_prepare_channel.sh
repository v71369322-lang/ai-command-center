#!/bin/bash
# Root operator installs a fixed prepare-only channel, never an unrestricted runner.
set -euo pipefail
umask 077
[ "$(id -u)" = 0 ]
[ "$(hostname -s)" = brain1 ]
[ "$(id -u acc-control)" = 1000 ]
[ "$(id -u acc-exec)" = 1001 ]
id acc-gh-runner >/dev/null
for target in /usr/local/libexec/acc-password-prepare-channel.py /usr/local/libexec/acc-password-prepare-fixed.sh /etc/systemd/system/acc-password-prepare-fixed.service /etc/systemd/system/acc-password-prepare-fixed.path /var/lib/acc-password-source-handoff /var/lib/acc-password-prepare-receipt /home/acc-control/f31; do
  [ ! -e "$target" ] || { echo "Existing target: $target; reconcile instead of overwriting"; exit 1; }
done
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
python3 - "$tmp" <<'PY'
import os,stat,sys
from pathlib import Path
source=Path('/var/lib/acc-gh-runner/bootstrap-password')
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
a2acbaedb2b176251f5d9791ea5ff6ab1f7f99554a377d4838d3110936ad884d  prepare_channel.py
169622da96d0002d77d2521a941aed5c3d37c2e7d602eb71467db91ced43b1a5  prepare_fixed_release.sh
27ed2eb23090e08bd9dbc082bfbc4e03d0bd45e2c0913d7ad6277ca3abc15051  acc-prepare-fixed.service
b649ac679c68d4a26992ef34f6292fdcc8c268d076f21eabd7243b9303b7721b  acc-prepare-fixed.path
SUMS
)
if ! (command -v git && python3.12 -c 'import venv,ensurepip') >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends git python3.12-venv
fi
install -d -m 0755 /usr/local/libexec
install -o root -g root -m 0444 "$tmp/prepare_channel.py" /usr/local/libexec/acc-password-prepare-channel.py
install -o root -g root -m 0444 "$tmp/prepare_fixed_release.sh" /usr/local/libexec/acc-password-prepare-fixed.sh
install -o root -g root -m 0644 "$tmp/acc-prepare-fixed.service" /etc/systemd/system/acc-password-prepare-fixed.service
install -o root -g root -m 0644 "$tmp/acc-prepare-fixed.path" /etc/systemd/system/acc-password-prepare-fixed.path
install -d -o acc-control -g acc-control -m 0700 /home/acc-control/f31 /var/lib/acc-password-source-handoff
install -o root -g root -m 0444 "$tmp/source.json" /var/lib/acc-password-source-handoff/source.json
install -d -o acc-control -g acc-gh-runner -m 2750 /var/lib/acc-password-prepare-receipt
systemctl daemon-reload
systemctl start acc-password-prepare-fixed.path
systemctl is-active acc-password-prepare-fixed.path
touch /var/lib/acc-gh-runner/bootstrap-password/operator.ready
echo PREPARE_CHANNEL_READY
