"""Existing broker/ledger sandbox stages for owner-supplied offline changes."""
import time

from ..isolated_coding import report, validate_payload
from ..store import Denied, canonical, digest
from .runner import CodingRunner


class IsolatedCodingRunner(CodingRunner):
    def execute(self, task):
        value = task['payload']
        validate_payload(value)
        if self.runtime.mode != 'rootless-required':
            raise Denied('isolated_coding_rootless_required')
        scope = value['specification']['scope']
        if self.limits.memory_mib > 256 or self.limits.cpu > .5 or self.limits.pids > 64:
            raise Denied('isolated_coding_runtime_limits')
        self.deadline = min(self.ledger.get(task['id'], task['fence'])['deadline'],
                            time.time() + scope['max_seconds'])
        with self.ledger.tx() as db:
            db.execute('UPDATE runs SET deadline=min(deadline,?) WHERE id=? AND fence=?',
                       (self.deadline, task['id'], task['fence']))
        try:
            base = {'operation_id': task['id'], 'fence': task['fence'], 'payload': value}
            expected = report(value)
            first = self.stage(task, {**base, 'mode': 'agent'})
            self.validate_result(first, expected, value)
            if not self.stop(self.name(task)):
                raise Denied('isolated_agent_stop_unconfirmed')
            with self.ledger.launch_lock():
                self.ledger.next_stage(task['id'], task['fence'])
                self.launch_attempted = False
            second = self.stage(task, {**base, 'mode': 'verify'})
            self.validate_result(second, expected, value)
            if first != second:
                raise Denied('isolated_independent_verifier_mismatch')
            if not self.stop(self.name(task)):
                raise Denied('isolated_verifier_stop_unconfirmed')
            artifact = canonical({**second, 'independent_verification': True})
            self.store.finish(task['id'], task['fence'], artifact, digest({**second, 'independent_verification': True}),
                              actual_cost=0)
        except Exception:
            stopped = self.quiesce(self.name(task)) if self.launch_attempted else True
            self.store.abort(task['id'], task['fence'], 'isolated_coding_failed', stopped)
            raise

    @staticmethod
    def validate_result(result, expected, value):
        checks = [{'command': argv, 'passed': True} for argv in value['specification']['verification_commands']]
        if canonical(result) != canonical({**expected, 'checks': checks, 'passed': True}):
            raise Denied('isolated_coding_verification_failed')
