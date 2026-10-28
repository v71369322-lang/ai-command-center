#!/bin/sh
# Only cloud-owned, networkless fixture containers. Never against a VPS.
set -eu
export BUILDX_CONFIG="${BUILDX_CONFIG:-$PWD/.runtime/buildx}"
export F1_SOURCE_REVISION="$(git rev-parse HEAD)"
if [ -n "${F1_BUILD_CA_FILE:-}" ]; then
    scripts/docker_local.sh build --build-arg F1_SOURCE_REVISION --secret "id=proxy_ca,src=$F1_BUILD_CA_FILE" -q \
        -f infra/vps/operations/Dockerfile.test -t acc-operations-proof:local .
else
    scripts/docker_local.sh build --build-arg F1_SOURCE_REVISION -q -f infra/vps/operations/Dockerfile.test -t acc-operations-proof:local .
fi
test "$(scripts/docker_local.sh image inspect acc-operations-proof:local --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" = "$F1_SOURCE_REVISION"
scripts/docker_local.sh run --rm --network=none --read-only \
    --cap-drop=ALL --cap-add=CHOWN --cap-add=SETUID --cap-add=SETGID \
    --security-opt=no-new-privileges --memory=256m --cpus=1 --pids-limit=64 \
    --tmpfs=/var/lib/acc-operations:size=16m,mode=755 \
    --tmpfs=/etc/acc-operations:size=1m,mode=755 \
    --tmpfs=/run:size=16m,mode=755 --tmpfs=/tmp:size=16m,mode=1777 \
    acc-operations-proof:local > .runtime/operations-container-proof.json
python3 -c 'import json;p=json.load(open(".runtime/operations-container-proof.json"));assert p["status"]=="PASS" and p["backend"]=="synthetic" and p["vps_test"] is False;print("Ubuntu 24.04 → distinct real UIDs → signed mailbox → duplicate blocked: PASS (synthetic backend, no VPS/rootless/systemd proof)")'
