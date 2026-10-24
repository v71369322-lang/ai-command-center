"""Credential-free sandbox steps orchestrated by trusted F1 broker + gateway."""
import hashlib
import time

from ..store import Denied, digest
from .gateway import Gateway, Uncertain
from .http_contract import GatewayProvider
from .remote_publication import RemotePublisher
from .runner import CodingRunner
from .spec import INITIAL, OBJECTIVE, PLAN, REPOSITORY, TEST_SOURCE
from .verification import inspect_result


class HttpCodingRunner(CodingRunner):
    def __init__(self, store, runtime, limits, ledger, gateway=None):
        super().__init__(store, runtime, limits, ledger)
        self.gateway = gateway or Gateway(store)
        self.gateway.runtime_guard = lambda: (
            time.time() < self.deadline and self.ledger.watchdog_ready(self.limits.watchdog_seconds)
            and self.ledger.get(self.current_task['id'], self.current_task['fence'])['phase'] in {'INTENT', 'ACTIVE'})

    def next_sandbox(self, task):
        if not self.stop(self.name(task)):
            raise Uncertain('sandbox_stop_unconfirmed')
        with self.ledger.launch_lock():
            self.ledger.next_stage(task['id'], task['fence'])
            self.launch_attempted = False

    def execute(self, task):
        self.current_task = task
        config = task['payload']['coding']
        self.deadline = min(self.ledger.get(task['id'], task['fence'])['deadline'], time.time() + config['max_seconds'])
        proposals, used_tokens = [], 0
        try:
            with self.store.transaction() as s:
                self.gateway.authority(s, task['id'], task['fence'])
            RemotePublisher(self.gateway, task).verify_repository()  # Before the first paid model request.
            provider = GatewayProvider(self.gateway, task)
            source, checks = INITIAL, None
            base = {'operation_id': task['id'], 'fence': task['fence'], 'coding': config}
            for attempt in range(1, min(config['max_iterations'], config['max_units']) + 1):
                if time.time() >= self.deadline:
                    raise Denied('coding_time_limit')
                self.store.coding_stage(task['id'], task['fence'], 'provider_running', plan=PLAN,
                                        summary='AI-провайдер готовит ограниченное изменение.', iteration=attempt)
                proposal = provider.propose({'repository': REPOSITORY, 'objective': OBJECTIVE,
                                             'base_sha': config['base_sha'], 'source': source,
                                             'acceptance': TEST_SOURCE, 'checks': checks, 'attempt': attempt})
                used_tokens += proposal.tokens
                if used_tokens > config['max_tokens']:
                    raise Denied('coding_token_limit')
                proposals.append(proposal.changes)
                result = self.stage(task, {**base, 'mode': 'external_iteration', 'proposals': proposals})
                report, _, snapshots = inspect_result(result, task['id'], task['fence'], config, allow_incomplete=True)
                source, checks = snapshots[-1]['calculator.py'], report['checks'][-1]['checks']
                self.store.coding_stage(task['id'], task['fence'], 'tests', test_runs=report['checks'],
                                        agent_result=result, summary='Проверки пройдены.' if checks['passed'] else
                                        'Проверки нашли ошибку. Выполняется ограниченное исправление.')
                self.next_sandbox(task)
                if checks['passed']:
                    break
            else:
                raise Denied('coding_attempt_limit')
            proof = self.stage(task, {**base, 'mode': 'verify', 'result': result})
            if proof != report or not proof['passed']:
                raise Denied('independent_verifier_mismatch')
            self.store.coding_stage(task['id'], task['fence'], 'verified', independent_proof=digest(proof),
                                    base_sha=config['base_sha'], final_sha=report['head_sha'],
                                    summary='Результат независимо проверен. Публикация ожидает.')
            pr = RemotePublisher(self.gateway, task).publish(result)
            summary = ('HTTP-mock сценарий завершён: изменение, исправление и draft PR проверены; реального AI-вызова не было.'
                       if self.gateway.config.mode == 'http_mock' else 'Результат независимо проверен; draft PR создан.')
            self.store.coding_stage(task['id'], task['fence'], 'complete', pr=pr, summary=summary,
                                    integration=self.gateway.status(task['id']))
            self.store.finish(task['id'], task['fence'], summary, hashlib.sha256(summary.encode()).hexdigest(),
                              actual_cost=len(proposals))
        except Exception as error:
            if isinstance(error, Uncertain):
                code, message = 'external_outcome_uncertain', 'Внешний результат неопределён. Повтор заблокирован до сверки.'
            elif isinstance(error, PermissionError):
                code, message = 'credential_not_connected', 'Credentials не подключены или их защищённое предоставление отклонено.'
            elif isinstance(error, Denied):
                code, message = str(error)[:80], 'Выполнение остановлено проверкой полномочий, лимитов или результата.'
            else:
                code, message = 'provider_or_verifier_contract_rejected', 'Ответ или результат проверки не соответствует контракту. PR не принят.'
            try:
                self.store.coding_stage(task['id'], task['fence'], 'external_stopped', failure=code, summary=message)
            except Exception:
                pass  # Cancellation/audit/PG failure must not be bypassed to update a report.
            stopped = self.quiesce(self.name(task))
            # HTTP uncertainty is distinct from confirmed sandbox termination.
            self.store.abort(task['id'], task['fence'], 'external_outcome_uncertain' if isinstance(error, Uncertain)
                             else 'external_coding_blocked', stopped and not isinstance(error, Uncertain),
                             actual_cost=len(proposals), usage_unknown=isinstance(error, Uncertain))
            raise
        finally:
            self.gateway.close()
