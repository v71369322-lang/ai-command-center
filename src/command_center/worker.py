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

from .config import Settings
from .local_docker import environment, run as docker
from .models import Control
from .store import Denied, Store
from .verifier import verify


class Runner:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def name(task):
        return f"acc-f1-{task['id']}-{task['fence']}"

    def stop(self, name):
        result = docker("rm", "--force", name)
        check = docker("inspect", name)
        # A failed inspect alone is not evidence of absence (daemon may be down).
        healthy = docker("info", "--format", "{{.ServerVersion}}")
        return healthy.returncode == 0 and check.returncode != 0 and (
            result.returncode == 0 or b"No such container" in result.stderr)

    def quiesce(self, name):
        stopped = docker("stop", "--time", "2", name)
        info = docker("inspect", name, "--format", "{{.State.Running}}")
        if info.returncode == 0:
            return info.stdout.strip() == b"false"
        return (b"No such container" in stopped.stderr and docker("info", "--format", "{{.ServerVersion}}").returncode == 0)

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
    def valid_isolation(info):
        h, c = info["HostConfig"], info["Config"]
        return (h["NetworkMode"] == "none" and h["ReadonlyRootfs"] and not h["Privileged"]
                and h["CapDrop"] == ["ALL"] and not h.get("CapAdd")
                and "no-new-privileges:true" in h["SecurityOpt"]
                and c["User"] == "65532:65532" and not info["Mounts"]
                and h["Memory"] == 128 * 1024 * 1024 and h["NanoCpus"] == 500_000_000
                and h["PidsLimit"] == 32 and not h.get("Binds")
                and not any(value.startswith("F1_") for value in c["Env"]))

    def execute(self, task):
        name = self.name(task)
        if shutil.disk_usage(".").free < 256 * 1024 * 1024:
            self.store.abort(task["id"], task["fence"], "host_disk_low", True)
            return
        if not self.store.pulse(task["id"], task["fence"]):
            self.store.abort(task["id"], task["fence"], "admission_revoked", True)
            return
        image = docker("image", "inspect", self.store.settings.executor_image, "--format", "{{json .}}")
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
                process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, env=environment())
                process.stdin.write(json.dumps(job, ensure_ascii=False, separators=(",", ":")).encode())
                process.stdin.close()
                selector.register(process.stdout, selectors.EVENT_READ, "output")
                selector.register(process.stderr, selectors.EVENT_READ, "errors")
                buffers = {"output": bytearray(), "errors": bytearray()}
                deadline = time.monotonic() + self.store.settings.timeout_seconds
                isolation_checked = False
                while selector.get_map() or process.poll() is None:
                    if time.monotonic() > deadline:
                        raise Denied("timeout")
                    if process.poll() is None and not self.store.pulse(task["id"], task["fence"]):
                        raise Denied("permission_or_lease_lost")
                    if not isolation_checked:
                        metadata = docker("inspect", name)
                        if metadata.returncode == 0:
                            if not self.valid_isolation(json.loads(metadata.stdout)[0]):
                                self.store.security_trip(task["id"], task["fence"])
                                raise Denied("isolation_policy_mismatch")
                            isolation_checked = True
                    for key, _ in selector.select(.2):
                        chunk = os.read(key.fd, 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                            continue
                        buffers[key.data].extend(chunk)
                        if len(buffers[key.data]) > 65536:
                            raise Denied("output_limit")
                raw = buffers["output"].decode()
                if process.wait(timeout=5) != 0:
                    raise Denied("executor_failed")
                if not isolation_checked:
                    metadata = docker("inspect", name)
                    if metadata.returncode or not self.valid_isolation(json.loads(metadata.stdout)[0]):
                        self.store.security_trip(task["id"], task["fence"])
                        raise Denied("isolation_unconfirmed")
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
    settings = Settings.load(identities_required=False)
    store, queue = Store(settings), broker(settings)
    runner = Runner(store)
    failures = 0
    while True:
        try:
            store.recover()
            for task in store.reconciliation_tasks():
                if task["state"] in {"RECONCILING", "CANCEL_REQUESTED"}:
                    runner.reconcile(task)
            store.dispatch(queue)
            event = queue.rpop("f1:work")
            if event:
                message = json.loads(event)
                task = store.claim(message["task_id"])
                if task:
                    runner.execute(task)
            failures = 0
        except Exception:
            # Failure is reflected by PG readiness/expired lease, not a fabricated success.
            failures = min(failures + 1, 5)
            time.sleep(min(2 ** failures, 30))
        time.sleep(.2)


if __name__ == "__main__":
    main()
