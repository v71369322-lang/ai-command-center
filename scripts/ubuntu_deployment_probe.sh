#!/bin/sh
# Cloud-only package/OS compatibility probe. Does not emulate a VPS boot.
set -eu
export BUILDX_CONFIG="${BUILDX_CONFIG:-$PWD/.runtime/buildx}"
if [ -n "${F1_BUILD_CA_FILE:-}" ]; then
    scripts/docker_local.sh build --secret "id=proxy_ca,src=$F1_BUILD_CA_FILE" -q \
        -f infra/vps/Dockerfile.ubuntu-test -t acc-f23-ubuntu-probe:local .
else
    scripts/docker_local.sh build -q -f infra/vps/Dockerfile.ubuntu-test -t acc-f23-ubuntu-probe:local .
fi
scripts/docker_local.sh run --rm --network=none --read-only --cap-drop=ALL --security-opt=no-new-privileges \
    --memory=256m --cpus=.5 --pids-limit=64 --tmpfs=/tmp:size=16m \
    acc-f23-ubuntu-probe:local > .runtime/f23-ubuntu-probe.json
python3 -c 'import json;d=json.load(open(".runtime/f23-ubuntu-probe.json"));assert d["os"]["ID"]=="ubuntu" and d["os"]["VERSION_ID"]=="24.04";print("Ubuntu 24.04 pinned image + prerequisite packages + networkless read-only probe: PASS (not a boot/rootless test)")'
