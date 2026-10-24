"""F2 stages reuse F1 admission, runtime policy, ledger, lease/fence and watchdog."""
import hashlib
import json
import os
import selectors
import shutil
import time

from ..store import Denied
from ..worker import Runner
from .contract import validate_payload
from .publication import prepare_draft
from .spec import PLAN
from .verification import inspect_result


class CodingRunner(Runner):
    def __init__(self, store, runtime, limits, ledger):
        if runtime is None or ledger is None or limits is None:
            raise ValueError('f1_runtime_authority_required')
        super().__init__(store, runtime, limits, ledger)

    def stage(self, task, job):
        if shutil.disk_usage('.').free < self.limits.min_free_mib * 1024 * 1024:
            raise Denied('host_disk_low')
        if not self.store.pulse(task['id'], task['fence']):
            raise Denied('coding_authority_lost')
        metadata = self.docker('image', 'inspect', self.store.settings.coding_image, '--format', '{{json .}}')
        if metadata.returncode:
            raise Denied('coding_image_unavailable')
        image = json.loads(metadata.stdout)
        if image['Config'].get('Labels', {}).get('org.opencontainers.image.revision') != self.store.settings.source_revision:
            raise Denied('coding_image_revision_mismatch')
        args = self.command(self.name(task), image['Id'])
        args[1] = '--host=' + self.runtime.endpoint
        for option, value in {'--cpus': self.limits.cpu, '--memory': f'{self.limits.memory_mib}m',
                              '--memory-swap': f'{self.limits.memory_mib}m', '--pids-limit': self.limits.pids,
                              '--ulimit': f'fsize={self.limits.file_kib * 1024}:{self.limits.file_kib * 1024}',
                              '--tmpfs': f'/work:rw,noexec,nosuid,nodev,size={self.limits.disk_mib}m,uid=65532,gid=65532,mode=0700'}.items():
            args[args.index(option) + 1] = str(value)
        position = args.index('--log-opt')
        args[position + 1] = f'max-size={self.limits.log_mib}m'
        args[position + 3] = f'max-file={self.limits.log_files}'
        process = self.spawn(task, args)
        try:
            raw = json.dumps(job, separators=(',', ':')).encode()
            if len(raw) > 65536:
                raise Denied('coding_transport_limit')
            process.stdin.write(raw)
            process.stdin.close()
            buffers = {'out': bytearray(), 'err': bytearray()}
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, 'out')
                selector.register(process.stderr, selectors.EVENT_READ, 'err')
                while selector.get_map() or process.poll() is None:
                    row = self.ledger.get(task['id'], task['fence'])
                    if (time.time() >= self.deadline or row['phase'] != 'ACTIVE'
                            or not self.ledger.watchdog_ready(self.limits.watchdog_seconds)
                            or not self.store.pulse(task['id'], task['fence'])):
                        raise Denied('coding_deadline_or_authority_lost')
                    for key, _ in selector.select(.1):
                        chunk = os.read(key.fd, 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                        else:
                            buffers[key.data].extend(chunk)
                            if len(buffers[key.data]) > self.limits.output_kib * 1024:
                                raise Denied('coding_output_limit')
            if process.wait(timeout=5) != 0:
                raise Denied('coding_process_failed')
            envelope = json.loads(buffers['out'])
            if (envelope['operation_id'] != task['id'] or type(envelope['fence']) is not int
                    or envelope['fence'] != task['fence']):
                raise Denied('coding_result_forged')
            return envelope['result']
        finally:
            if process.poll() is None:
                self.quiesce(self.name(task))
                try:
                    process.wait(timeout=5)
                except Exception:
                    process.kill()
                    process.wait(timeout=5)

    def execute(self, task):
        validate_payload(task['payload'])
        config = task['payload']['coding']
        self.deadline = min(self.ledger.get(task['id'], task['fence'])['deadline'], time.time() + config['max_seconds'])
        with self.ledger.tx() as db:
            db.execute('UPDATE runs SET deadline=min(deadline,?) WHERE id=? AND fence=?',
                       (self.deadline, task['id'], task['fence']))
        usage = None
        try:
            self.store.coding_stage(task['id'], task['fence'], 'coding', plan=PLAN,
                                    summary='Разработчик выполняет задачу в отдельной тестовой ветке.')
            base = {'operation_id': task['id'], 'fence': task['fence'], 'coding': config}
            result = self.stage(task, {**base, 'mode': 'agent'})
            candidate_usage = result.get('usage', {})
            if (candidate_usage.get('synthetic') is True and type(candidate_usage.get('units')) is int
                    and 0 <= candidate_usage['units'] <= config['max_units']):
                usage = candidate_usage['units']
            if result.get('status') != 'ready_for_verification':
                self.store.coding_stage(task['id'], task['fence'], 'failed',
                                        summary='Задача остановлена: ' + str(result.get('status', 'invalid_result'))[:64],
                                        failure=result.get('status'), provider_usage=candidate_usage)
                raise Denied('coding_attempts_or_scope_blocked')
            report, _, snapshots = inspect_result(result, task['id'], task['fence'], config)
            self.store.coding_stage(task['id'], task['fence'], 'verification', agent_result=result,
                                    summary='Изменения получены. Независимая проверка повторяет тесты.')
            if not self.stop(self.name(task)):
                raise Denied('agent_container_stop_unconfirmed')
            with self.ledger.launch_lock():
                self.ledger.next_stage(task['id'], task['fence'])
                self.launch_attempted = False
            proof = self.stage(task, {**base, 'mode': 'verify', 'result': result})
            if proof != report:
                raise Denied('independent_verifier_mismatch')
            draft = prepare_draft(task['id'], report, snapshots[-1])
            summary = 'Функция исправлена. Первая проверка нашла ошибку, агент исправил её; независимая проверка пройдена. PR подготовлен в mock-режиме, не опубликован.'
            self.store.coding_stage(task['id'], task['fence'], 'complete', test_runs=report['checks'],
                                    provider_usage=result['usage'], base_sha=report['base_sha'],
                                    final_sha=report['head_sha'], pr=draft, summary=summary,
                                    verification_digest=hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest())
            self.store.finish(task['id'], task['fence'], summary, hashlib.sha256(summary.encode()).hexdigest(), actual_cost=usage)
        except Exception:
            stopped = self.quiesce(self.name(task))
            self.store.abort(task['id'], task['fence'], 'coding_failed', stopped,
                             actual_cost=usage or 0, usage_unknown=usage is None)
            raise
