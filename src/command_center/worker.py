"""Trusted local Docker launcher. NEVER install its socket in an executor.
Docker daemon authority is a deployment gate; this is not a restricted Docker proxy.
"""
import json
import os
import subprocess
import selectors
import shutil
import time

import redis

from .local_docker import environment, run as docker
from .limits import CircuitBreaker
from .models import Control
from .store import Denied
from .verifier import verify


class Runner:
    def __init__(self, store, runtime=None, limits=None, ledger=None):
        self.store = store
        self.runtime, self.limits, self.ledger = runtime, limits, ledger
        self.launch_attempted = False

    def docker(self, *args, **kwargs):
        return (self.runtime.call if self.runtime else docker)(*args, **kwargs)

    def started(self, task):
        if self.ledger:
            self.ledger.phase(task['id'], task['fence'], 'ACTIVE')

    def spawn(self, task, args):
        def launch():
            self.launch_attempted = True
            return subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, env=environment())
        if not self.ledger:
            return launch()
        with self.ledger.launch_lock():
            record = self.ledger.get(task['id'], task['fence'])
            if record['phase'] != 'INTENT' or record['deadline'] <= time.time() or not self.ledger.watchdog_ready(self.limits.watchdog_seconds):
                raise Denied('runtime_grant_revoked')
            process = launch()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                result = self.docker('inspect', self.name(task))
                if result.returncode == 0:
                    if not self.valid_isolation(json.loads(result.stdout)[0], self.limits):
                        self.store.security_trip(task['id'], task['fence'])
                        break
                    self.started(task)
                    return process
                if process.poll() is not None:
                    break
                time.sleep(.05)
            process.kill()
            process.wait(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()
            self.ledger.phase(task['id'], task['fence'], 'UNCERTAIN')
            raise Denied('launch_outcome_unconfirmed')

    @staticmethod
    def name(task):
        return f"acc-f1-{task['id']}-{task['fence']}"

    def stop(self, name):
        result = self.docker("rm", "--force", name)
        check = self.docker("inspect", name)
        # A failed inspect alone is not evidence of absence (daemon may be down).
        healthy = self.docker("info", "--format", "{{.ServerVersion}}")
        return healthy.returncode == 0 and check.returncode != 0 and (
            result.returncode == 0 or b"No such container" in result.stderr)

    def quiesce(self, name):
        stopped = self.docker("stop", "--time", "2", name)
        info = self.docker("inspect", name, "--format", "{{.State.Running}}")
        if info.returncode == 0:
            return info.stdout.strip() == b"false"
        return (b"No such container" in stopped.stderr and self.docker("info", "--format", "{{.ServerVersion}}").returncode == 0)

    @staticmethod
    def command(name, image_id):
        return ["docker", "--host=unix:///var/run/docker.sock", "run", "--name", name,
                "--label", "acc.scope=f1", "--network", "none", "--read-only",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                "--user", "65532:65532", "--cpus", "0.5", "--memory", "128m",
                "--memory-swap", "128m", "--pids-limit", "32", "--ulimit", "fsize=65536:65536",
                "--log-driver", "local", "--log-opt", "max-size=1m", "--log-opt", "max-file=2",
                "--tmpfs", "/work:rw,noexec,nosuid,nodev,size=16m,uid=65532,gid=65532,mode=0700",
                "--env", "HTTP_PROXY=", "--env", "HTTPS_PROXY=", "--env", "ALL_PROXY=",
                "--env", "http_proxy=", "--env", "https_proxy=", "--env", "all_proxy=",
                "--interactive", image_id]

    @staticmethod
    def valid_isolation(info, limits=None):
        h, c = info["HostConfig"], info["Config"]
        return (h["NetworkMode"] == "none" and h["ReadonlyRootfs"] and not h["Privileged"]
                and h["CapDrop"] == ["ALL"] and not h.get("CapAdd")
                and "no-new-privileges:true" in h["SecurityOpt"]
                and c["User"] == "65532:65532" and not info["Mounts"]
                and h["Memory"] == (limits.memory_mib if limits else 128) * 1024 * 1024
                and h["NanoCpus"] == int((limits.cpu if limits else .5) * 1_000_000_000)
                and h["PidsLimit"] == (limits.pids if limits else 32) and not h.get("Binds")
                and not any(value.startswith("F1_") for value in c["Env"]))

    def execute(self, task):
        if task['payload']['kind'] not in {'render', 'approved_render'}:
            raise Denied('synthetic_runner_task_scope')
        name = self.name(task)
        if shutil.disk_usage(".").free < (self.limits.min_free_mib if self.limits else 256) * 1024 * 1024:
            self.store.abort(task["id"], task["fence"], "host_disk_low", True)
            return
        if not self.store.pulse(task["id"], task["fence"]):
            self.store.abort(task["id"], task["fence"], "admission_revoked", True)
            return
        image = self.docker("image", "inspect", self.store.settings.executor_image, "--format", "{{json .}}")
        if image.returncode:
            self.store.abort(task["id"], task["fence"], "verified_no_effect", True)
            return
        metadata = json.loads(image.stdout)
        image_id = metadata["Id"]
        if metadata["Config"].get("Labels", {}).get("org.opencontainers.image.revision") != self.store.settings.source_revision:
            self.store.abort(task["id"], task["fence"], "verified_no_effect", True)
            raise Denied("executor_revision_mismatch")
        with self.store.transaction() as s:
            current = self.store.task(s, task["id"])
            if current.fence != task["fence"] or current.state != "RUNNING":
                raise Denied("stale_launch")
            self.store.audit(s, "container_launch_intent", "worker", task["id"], fence=task["fence"], image_id=image_id)
        if not self.store.pulse(task["id"], task["fence"]):
            self.store.abort(task["id"], task["fence"], "admission_revoked", True)
            return
        job = {"operation_id": task["id"], "fence": task["fence"], "values": task["payload"]["values"]}
        process = None
        try:
            with selectors.DefaultSelector() as selector:
                args = self.command(name, image_id)
                if self.runtime:
                    args[1] = '--host=' + self.runtime.endpoint
                if self.limits:
                    for option, value in {'--cpus': self.limits.cpu, '--memory': str(self.limits.memory_mib) + 'm',
                                          '--memory-swap': str(self.limits.memory_mib) + 'm',
                                          '--pids-limit': self.limits.pids,
                                          '--ulimit': f'fsize={self.limits.file_kib * 1024}:{self.limits.file_kib * 1024}',
                                          '--tmpfs': f'/work:rw,noexec,nosuid,nodev,size={self.limits.disk_mib}m,uid=65532,gid=65532,mode=0700'}.items():
                        args[args.index(option) + 1] = str(value)
                    position = args.index('--log-opt')
                    args[position + 1] = f'max-size={self.limits.log_mib}m'
                    args[position + 3] = f'max-file={self.limits.log_files}'
                process = self.spawn(task, args)
                process.stdin.write(json.dumps(job, ensure_ascii=False, separators=(",", ":")).encode())
                process.stdin.close()
                selector.register(process.stdout, selectors.EVENT_READ, "output")
                selector.register(process.stderr, selectors.EVENT_READ, "errors")
                buffers = {"output": bytearray(), "errors": bytearray()}
                deadline = time.monotonic() + (self.limits.wall_seconds if self.limits else self.store.settings.timeout_seconds)
                isolation_checked = False
                while selector.get_map() or process.poll() is None:
                    if self.ledger and (not self.ledger.watchdog_ready(self.limits.watchdog_seconds) or
                                        self.ledger.get(task['id'], task['fence'])['phase'] != 'ACTIVE'):
                        raise Denied('watchdog_or_runtime_authority_lost')
                    if time.monotonic() > deadline:
                        raise Denied("timeout")
                    if process.poll() is None and not self.store.pulse(task["id"], task["fence"]):
                        raise Denied("permission_or_lease_lost")
                    if not isolation_checked:
                        metadata = self.docker("inspect", name)
                        if metadata.returncode == 0:
                            if not self.valid_isolation(json.loads(metadata.stdout)[0], self.limits):
                                self.store.security_trip(task["id"], task["fence"])
                                raise Denied("isolation_policy_mismatch")
                            isolation_checked = True
                            self.started(task)
                    for key, _ in selector.select(.2):
                        chunk = os.read(key.fd, 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                            continue
                        buffers[key.data].extend(chunk)
                        if len(buffers[key.data]) > (self.limits.output_kib * 1024 if self.limits else 65536):
                            raise Denied("output_limit")
                raw = buffers["output"].decode()
                if process.wait(timeout=5) != 0:
                    raise Denied("executor_failed")
                if not isolation_checked:
                    metadata = self.docker("inspect", name)
                    if metadata.returncode or not self.valid_isolation(json.loads(metadata.stdout)[0], self.limits):
                        self.store.security_trip(task["id"], task["fence"])
                        raise Denied("isolation_unconfirmed")
                    self.started(task)
                manifest = json.loads(raw)
                if (manifest["operation_id"] != task["id"] or type(manifest["fence"]) is not int
                        or manifest["fence"] != task["fence"]):
                    raise Denied("forged_result")
                artifact, checksum = verify(task["payload"], raw)
                self.store.finish(task["id"], task["fence"], artifact, checksum)
        except Exception:
            # Never include exception/daemon output in audit: it may contain sensitive metadata.
            stopped = self.quiesce(name)
            self.store.abort(task["id"], task["fence"], "execution_failed", stopped)
            raise
        finally:
            if process is not None and process.poll() is None:
                self.quiesce(name)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            # Artifacts are committed before disposal. On DB failure retain container evidence.
            try:
                if self.store.get(task["id"])["state"] in {"SUCCEEDED", "CANCELLED", "FAILED"}:
                    self.stop(name)
            except Exception:
                pass

    def reconcile(self, task):
        """Fixed synthetic executor has NO effects outside its disposable container.
Stop and verify absence before permitting a new separately admitted attempt.
No such claim is valid for a future real provider.
"""
        if task['payload']['kind'] not in {'render', 'approved_render'}:
            raise Denied('synthetic_reconciliation_task_scope')
        if not self.stop(self.name(task)):
            return False
        with self.store.transaction() as s:
            current = self.store.task(s, task["id"])
            if current.fence != task["fence"] or current.state not in {"RECONCILING", "CANCEL_REQUESTED"}:
                return False
            c = s.get(Control, 1)
            c.reserved -= current.reserved
            current.reserved = 0
            current.state = "CANCELLED" if current.state == "CANCEL_REQUESTED" else "FAILED"
            current.reason = "verified_no_effect"
            self.store.audit(s, "reconciled_container_absent", "reconciler", current.id, fence=current.fence)
            return True


def broker(settings):
    return redis.Redis.from_url(settings.redis_url, password=settings.redis_password,
                                socket_connect_timeout=2, socket_timeout=2, decode_responses=True)


def main():
    # Scheduler has Redis + scoped Unix RPC only. No PG credentials or Docker socket.
    from .broker_client import BrokerClient
    client = BrokerClient.from_env()
    queue = redis.Redis.from_url(os.environ.get('F1_REDIS_URL', 'redis://redis:6379/0'),
                                 password=open(os.environ['F1_REDIS_PASSWORD_FILE']).read().strip(),
                                 decode_responses=True, socket_timeout=2, socket_connect_timeout=2)
    failures = 0
    circuit = CircuitBreaker()
    while True:
        if not circuit.admit():
            time.sleep(1)
            continue
        try:
            client.request({'action': 'worker_online', 'revision': os.environ['F1_SOURCE_REVISION']})
            event = queue.rpop("f1:work")
            if event:
                message = json.loads(event)
                run = client.request({'action': 'submit', 'task_id': message['task_id'],
                                      'revision': os.environ['F1_SOURCE_REVISION']})
                if run.get('fence'):
                    while True:
                        status = client.request({'action': 'heartbeat', 'task_id': message['task_id'],
                                                 'fence': run['fence']})
                        if status['phase'] in {'DONE', 'UNCERTAIN'}:
                            break
                        time.sleep(.25)
            failures = 0
            circuit.success()
        except Exception:
            # Failure is reflected by PG readiness/expired lease, not a fabricated success.
            failures = min(failures + 1, 5)
            circuit.failure()
            time.sleep(min(2 ** failures, 30))
        time.sleep(.2)


if __name__ == "__main__":
    main()
