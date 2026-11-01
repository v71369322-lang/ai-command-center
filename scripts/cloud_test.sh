#!/bin/sh
set -eu
export F1_SOURCE_REVISION="$(git rev-parse HEAD)"
export F1_DB_USER=f1_app
export F1_DOCKER_GID="$(stat -c %g /var/run/docker.sock)"
export F1_DB_HOST="$(scripts/docker_local.sh inspect acc-f1-db-1 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')"
export F1_DB_PORT=5432
f1_redis_address="$(scripts/docker_local.sh inspect acc-f1-redis-1 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')"
export F1_REDIS_URL="redis://$f1_redis_address:6379/0"
export F1_DB_PASSWORD_FILE="$PWD/.runtime/secrets/db_password"
export F1_REDIS_PASSWORD_FILE="$PWD/.runtime/secrets/redis_password"
export F1_IDENTITIES_FILE="$PWD/.runtime/secrets/identities.json"
F1_DB_USER=f1_admin F1_DB_PASSWORD_FILE="$PWD/.runtime/secrets/db_admin_password" \
F1_RUNTIME_PASSWORD_FILE="$PWD/.runtime/secrets/db_runtime_password" \
F1_APP_PASSWORD_FILE="$PWD/.runtime/secrets/db_password" .venv/bin/python -m command_center.admin
.venv/bin/pytest -q --tb=short --junitxml=.runtime/test-results.xml "$@"
