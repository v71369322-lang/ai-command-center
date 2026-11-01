#!/bin/bash
# Owner-approved initial source access only. No network, GitHub write or deployment.
set -euo pipefail
set +x
umask 077
[ "$#" = 0 ]
[ "$(id -u)" = 0 ]
[ "$(hostname -s)" = brain1 ]
[ "$(id -u acc-control)" = 1000 ]
cd /
python3 -I - <<'PY'
import os,time
until = int(os.environ.get('ACC_SOURCE_KEY_APPROVED_UNTIL', '0'))
if not int(time.time()) < until <= int(time.time()) + 3600:
    raise SystemExit('SOURCE_KEY_APPROVAL_EXPIRED_OR_MISSING')
PY
directory=/home/acc-control/f34-source-access
[ ! -e "$directory" ] && [ ! -L "$directory" ]
/usr/sbin/runuser -u acc-control -- /bin/bash -c '
  set -euo pipefail
  set +x
  umask 077
  cd /home/acc-control
  mkdir -m 700 f34-source-access
  /usr/bin/ssh-keygen -q -t ed25519 -N "" \
    -C acc-command-center-source-readonly \
    -f /home/acc-control/f34-source-access/id_ed25519
  printf "%s\n" "github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl" \
    > /home/acc-control/f34-source-access/github_known_hosts
  chmod 600 /home/acc-control/f34-source-access/github_known_hosts
  /usr/bin/cat /home/acc-control/f34-source-access/id_ed25519.pub
  /usr/bin/ssh-keygen -lf /home/acc-control/f34-source-access/id_ed25519.pub -E sha256
'
echo SOURCE_PUBLIC_KEY_READY_NOT_CONNECTED
