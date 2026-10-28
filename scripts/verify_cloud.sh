#!/bin/sh
# Only the owned, synthetic acc-f1 project. Never run against production data.
set -eu
export F1_SOURCE_REVISION="$(git rev-parse HEAD)"
export F1_RUNTIME_UID="$(id -u)" F1_RUNTIME_GID="$(id -g)"
export F1_DOCKER_GID="$(stat -c %g /var/run/docker.sock)"
export BUILDX_CONFIG="${BUILDX_CONFIG:-$PWD/.runtime/buildx}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PWD/.runtime/uv-cache}"
mkdir -p .runtime
.venv/bin/python scripts/prepare_hardening.py
if [ -n "$(git status --porcelain)" ]; then
    echo 'A clean source tree is required for final evidence.' >&2
    exit 1
fi
dkr() {
    scripts/docker_local.sh "$@"
}
cleanup() { dkr compose --profile worker stop > .runtime/stop.log 2>&1 || true; }
trap cleanup EXIT
.venv/bin/ruff check src tests scripts
.venv/bin/python scripts/export_contract.py --check
.venv/bin/python scripts/check_secrets.py
.venv/bin/python scripts/security_checks.py
git diff --check
npm run --prefix web build
dkr compose --profile worker stop api worker runtime-broker watchdog > .runtime/pre-test-stop.log 2>&1 || true
dkr compose up -d db redis
dkr build --build-arg F1_SOURCE_REVISION -q -f Dockerfile.executor -t acc-f1-executor:local .
if [ -n "${F1_BUILD_CA_FILE:-}" ]; then
    dkr build --build-arg F1_SOURCE_REVISION --secret "id=proxy_ca,src=$F1_BUILD_CA_FILE" --target app -q -t acc-f1-app:local .
    dkr build --build-arg F1_SOURCE_REVISION --secret "id=proxy_ca,src=$F1_BUILD_CA_FILE" --target worker -q -t acc-f1-worker:local .
    dkr build --build-arg F1_SOURCE_REVISION --secret "id=proxy_ca,src=$F1_BUILD_CA_FILE" --target broker -q -t acc-f1-broker:local .
else
    dkr build --build-arg F1_SOURCE_REVISION --target app -q -t acc-f1-app:local .
    dkr build --build-arg F1_SOURCE_REVISION --target worker -q -t acc-f1-worker:local .
    dkr build --build-arg F1_SOURCE_REVISION --target broker -q -t acc-f1-broker:local .
fi
if [ -n "${F1_BUILD_CA_FILE:-}" ]; then
    dkr build --build-arg F1_SOURCE_REVISION --secret "id=proxy_ca,src=$F1_BUILD_CA_FILE" --target coding -q -t acc-f2-executor:local .
else
    dkr build --build-arg F1_SOURCE_REVISION --target coding -q -t acc-f2-executor:local .
fi
scripts/cloud_test.sh
.venv/bin/python scripts/isolated_restore_drill.py
.venv/bin/python scripts/telegram_transition_smoke.py
dkr compose --profile worker up -d --no-build api runtime-broker watchdog worker
.venv/bin/python scripts/container_smoke.py
dkr compose --profile worker restart api worker runtime-broker
.venv/bin/python scripts/container_smoke.py --check-persisted
.venv/bin/python scripts/hardening_smoke.py
.venv/bin/python scripts/coding_smoke.py
.venv/bin/python scripts/runtime_boundaries.py
.venv/bin/python scripts/telegram_service_smoke.py
.venv/bin/python scripts/deployment_smoke.py
dkr image inspect acc-f1-app:local acc-f1-worker:local acc-f1-executor:local \
    --format '{{.Id}} {{index .Config.Labels "org.opencontainers.image.revision"}}' > .runtime/images.txt
echo "Final cloud verification passed for $F1_SOURCE_REVISION"
