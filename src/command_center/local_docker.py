"""All cloud Docker operations are pinned to the existing local Unix daemon."""
import os
import subprocess


SELECTORS = ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH')


def environment():
    env = dict(os.environ)
    for name in SELECTORS:
        env.pop(name, None)
    # Preserve registry/proxy/CA bindings; never discover or print their values.
    return env


def run(*args, timeout=10, **kwargs):
    return subprocess.run(['docker', '--host=unix:///var/run/docker.sock', *args],
                          env=environment(), capture_output=True, timeout=timeout, **kwargs)
