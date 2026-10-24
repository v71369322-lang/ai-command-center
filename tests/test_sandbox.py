import json
import subprocess
import time
import pytest
from uuid import uuid4

from command_center.worker import Runner, docker


def inspected_state(name, *, wait_for_oom=False, seconds=10):
    # Docker can report process exit before its asynchronous OOM event updates
    # inspect state. Keep the container until that evidence arrives, boundedly.
    # A missing OOM flag is still a failure; exit 137 alone is not accepted.
    deadline = time.monotonic() + seconds
    while True:
        inspect = docker('inspect', name, '--format', '{{json .}}')
        assert inspect.returncode == 0
        info = json.loads(inspect.stdout)
        if not wait_for_oom or info['State']['OOMKilled'] or time.monotonic() >= deadline:
            return info
        time.sleep(.05)


def sandbox(code, *, wait_for_oom=False):
    name = "acc-f1-probe-" + uuid4().hex
    args = Runner.command(name, "acc-f1-executor:local")
    args[-1:-1] = ["--entrypoint", "python"]
    args.extend(["-I", "-c", code])
    try:
        result = subprocess.run(args, input=b"", capture_output=True, timeout=15)
        return result, inspected_state(name, wait_for_oom=wait_for_oom)
    finally:
        docker("rm", "--force", name)


def test_T08_actual_container_security_boundaries():
    code = '''
import os,socket,json
result={'uid':os.getuid(),'docker_socket':os.path.exists('/var/run/docker.sock'),'ssh_home':os.path.exists('/root/.ssh')}
for name,path in [('root_write','/forbidden'),('code_write','/executor.py')]:
 try:
  with open(path,'w') as f: f.write('forbidden')
  result[name]=True
 except OSError: result[name]=False
try:
 socket.create_connection(('192.0.2.1',9),timeout=.2)
 result['network']=True
except OSError: result['network']=False
print(json.dumps(result))
'''
    result, info = sandbox(code)
    assert result.returncode == 0
    facts = json.loads(result.stdout)
    assert facts == {'uid':65532,'docker_socket':False,'ssh_home':False,'root_write':False,'code_write':False,'network':False}
    assert Runner.valid_isolation(info)
    config = info['HostConfig']
    assert config['NetworkMode'] == 'none'
    assert config['ReadonlyRootfs']
    assert config['CapDrop'] == ['ALL']
    assert 'no-new-privileges:true' in config['SecurityOpt']
    assert not info['Mounts']
    assert config['Memory'] == 128 * 1024 * 1024
    assert config['NanoCpus'] == 500_000_000
    assert config['PidsLimit'] == 32
    config['Privileged'] = True
    assert not Runner.valid_isolation(info)
    assert all(not entry.startswith('F1_') for entry in info['Config']['Env'])


def test_T10_actual_memory_limit():
    result, info = sandbox("data = bytearray(256 * 1024 * 1024)", wait_for_oom=True)
    assert result.returncode == 137
    assert info['State']['OOMKilled']


@pytest.mark.parametrize('delayed', [True, False])
def test_memory_probe_waits_for_evidence_but_never_invents_oom(monkeypatch, delayed):
    import sys
    clock = iter(range(20))
    calls = []
    def inspect(*args):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, json.dumps({
            'State': {'OOMKilled': delayed and len(calls) >= 2}}).encode())
    monkeypatch.setattr(sys.modules[__name__], 'docker', inspect)
    monkeypatch.setattr(time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(time, 'sleep', lambda _: None)
    info = inspected_state('synthetic-container', wait_for_oom=True, seconds=3)
    assert info['State']['OOMKilled'] is delayed
    assert len(calls) >= 2


def test_T10_actual_file_limit():
    result, info = sandbox("from pathlib import Path; Path('/work/large.json').write_bytes(b'x'*131072)")
    assert result.returncode != 0
    assert 'File too large' in result.stderr.decode()


def test_T10_actual_disk_limit():
    result, info = sandbox("from pathlib import Path\nfor i in range(400): Path('/work/'+str(i)+'.json').write_bytes(b'x'*60000)")
    assert result.returncode != 0
    assert 'No space left on device' in result.stderr.decode()


@pytest.mark.parametrize("mode", ["cancel", "timeout"])
def test_T09_actual_running_container_cancel(store, mode):
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    import time
    from command_center.store import Denied
    builder = "acc-f1-sleep-build-" + uuid4().hex
    image = "acc-f1-test-sleeper:local"
    assert docker("create", "--name", builder, "acc-f1-executor:local").returncode == 0
    try:
        assert docker("commit", "--change", 'ENTRYPOINT ["python","-I","-c","import time; time.sleep(8)"]', builder, image).returncode == 0
    finally:
        docker("rm", builder)
    original = store.settings
    store.settings = replace(original, executor_image=image, timeout_seconds=3 if mode == "timeout" else 30)
    task = store.create("owner", "running-cancel", {"kind":"render","values":{"x":"synthetic"},"cost":0,"dependency":None})
    claimed = store.claim(task["id"])
    runner = Runner(store)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(runner.execute, claimed)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                check = docker("inspect", runner.name(claimed), "--format", "{{.State.Running}}")
                if check.returncode == 0 and check.stdout.strip() == b"true":
                    break
                time.sleep(.1)
            else:
                raise AssertionError("container_never_started")
            if mode == "cancel":
                store.cancel("owner", task["id"])
            with pytest.raises(Denied):
                future.result(timeout=10)
        assert store.get(task["id"])["state"] == ("CANCELLED" if mode == "cancel" else "FAILED")
        assert runner.stop(runner.name(claimed))
    finally:
        store.settings = original
        docker("image", "rm", image)


def test_T10_actual_pid_limit():
    result, _ = sandbox('''
import os,time,json
children=[]
blocked=False
for i in range(40):
 try:
  pid=os.fork()
 except OSError:
  blocked=True
  break
 if pid==0:
  time.sleep(1)
  os._exit(0)
 children.append(pid)
for pid in children: os.waitpid(pid,0)
print(json.dumps({'blocked':blocked,'children':len(children)}))
''')
    assert result.returncode == 0
    facts = json.loads(result.stdout)
    assert facts['blocked'] and facts['children'] < 32


def test_T10_actual_cpu_quota():
    result, _ = sandbox('''
import time,json
start=time.monotonic(); cpu=time.process_time()
while time.monotonic()-start<2: pass
print(json.dumps({'wall':time.monotonic()-start,'cpu':time.process_time()-cpu}))
''')
    assert result.returncode == 0
    facts = json.loads(result.stdout)
    assert facts['cpu'] / facts['wall'] < .8
