#!/bin/sh
set -eu
umask 077
printf 'bind 0.0.0.0\nprotected-mode yes\nappendonly no\nmaxmemory 64mb\nmaxmemory-policy noeviction\nrequirepass %s\n' "$(cat /run/secrets/redis_password)" > /tmp/redis.conf
exec redis-server /tmp/redis.conf
