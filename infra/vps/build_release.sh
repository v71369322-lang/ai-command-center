#!/bin/sh
# Future authorized local build; never remote. No push, registry login or secrets.
set -eu
: "${ACC_CONTROL_UID:?Dedicated control UID required}"
: "${ACC_EXECUTION_UID:?Separate execution UID required}"
[ "$(id -u)" = "$ACC_CONTROL_UID" ]
[ "$ACC_CONTROL_UID" != "$ACC_EXECUTION_UID" ]
[ -z "$(git status --porcelain)" ]
export F1_SOURCE_REVISION="$(git rev-parse HEAD)"
control="unix:///run/user/$ACC_CONTROL_UID/docker.sock"
execution="unix:///run/user/$ACC_EXECUTION_UID/docker.sock"
local_docker() {
    env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker "$@"
}
for endpoint in "$control" "$execution"; do
    local_docker --host="$endpoint" info --format '{{json .SecurityOptions}}' | python3 -c \
        'import json,sys;assert any("rootless" in v for v in json.load(sys.stdin))'
done
local_docker --host="$control" build --build-arg F1_SOURCE_REVISION -f Dockerfile.executor -t acc-f1-executor:local .
for target in app worker broker coding; do
    tag="acc-f1-$target:local"
    if [ "$target" = coding ]; then tag=acc-f2-executor:local; fi
    local_docker --host="$control" build --build-arg F1_SOURCE_REVISION --target "$target" -t "$tag" .
done
# Immutable objects transferred locally; execution daemon cannot reach GitHub.
archive="$(mktemp)"
trap 'rm -f "$archive"' EXIT HUP INT TERM
chmod 600 "$archive"
local_docker --host="$control" save -o "$archive" acc-f1-executor:local acc-f2-executor:local
local_docker --host="$execution" load -i "$archive"
printf 'Local images built for %s; no deployment or external integrations enabled.\n' "$F1_SOURCE_REVISION"
