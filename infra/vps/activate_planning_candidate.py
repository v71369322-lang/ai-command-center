#!/usr/bin/env python3
"""Exact planning activation/reconciliation through existing deployment interlocks."""
import argparse
import fcntl
import json
import os
from pathlib import Path

from command_center.deployment import load_bundle
from command_center.deployment_profile import atomic_json, checksum
from command_center.planning_candidate import capability, inspect, read_json
from command_center.store import digest
from command_center.telegram_transport import connection

from apply_reconciled_telegram_candidate import ReconciledUpdate, apply as apply_transition, deadline


class PlanningUpdate(ReconciledUpdate):
    def postcheck(self):
        result = super().postcheck()
        # Trusted maintenance inspection: no gateway/client/credential construction.
        self.tool('''from sqlalchemy import select
from command_center.config import Settings
from command_center.store import Store
from command_center.models import ExternalAction
from command_center.coding.gateway import Gateway
s=Store(Settings.load())
s.checkpoint()
state=s.snapshot()
assert state['halted'] and not state['recovery'] and state['budget']['uncertain']==0
with s.transaction() as tx:
    rows=list(tx.scalars(select(ExternalAction)))
    Gateway.check_ledger(tx,rows)
    assert all(row.state=='COMPLETE' and row.reserved==0 for row in rows)
''')
        self.engine.run('exec', 'acc-f23-runtime-broker-1', 'python', '-c',
            'import os;from command_center.runtime_ledger import RuntimeLedger;'
            'from command_center.runtime_policy import RuntimeLimits;'
            'l=RuntimeLedger(os.environ["F1_RUNTIME_LEDGER"]);l.verify();'
            'assert not l.runs();assert l.worker_fresh(os.environ["F1_SOURCE_REVISION"],RuntimeLimits.load().heartbeat_seconds)')
        return {**result, 'planning_runtime_ready': True, 'admission_halted': True,
                'financial_ledger_verified': True, 'paid_calls_authorized': False}


class PlanningScope:
    def __init__(self, previous_pin, candidate_pin, preparation_pin, capability_pin):
        self.previous, self.candidate = previous_pin, candidate_pin
        self.preparation, self.capability = preparation_pin, capability_pin

    def validate(self, previous, target, directory, receipt):
        inspect(directory, self.candidate, self.preparation)
        if (checksum(previous) != self.previous or receipt['previous_bundle'] != self.previous
                or checksum(target) != self.candidate or digest(capability(target)) != self.capability):
            raise ValueError('planning_exact_access_and_preparation_approvals_required')
        return {'purpose': 'planning-activation.v1', 'preparation_digest': self.preparation,
                'control_capability': self.capability}

    @staticmethod
    def controller(target, directory):
        return PlanningUpdate(target, directory)


def apply(previous_directory, candidate_directory, approved_previous, approved_candidate,
          approved_until, approved_preparation, approved_capability):
    scope = PlanningScope(approved_previous, approved_candidate, approved_preparation, approved_capability)
    return apply_transition(previous_directory, candidate_directory, approved_previous,
        approved_candidate, approved_until, _planning=scope)


def reconcile(previous_directory, candidate_directory, approved_previous, approved_candidate,
              approved_until, approved_preparation, approved_capability, *, _scope=None):
    deadline(approved_until)
    directory = Path(candidate_directory)
    previous, target = load_bundle(previous_directory), load_bundle(directory)
    scope = _scope or PlanningScope(approved_previous, approved_candidate, approved_preparation, approved_capability)
    extra = scope.validate(previous, target, directory, read_json(directory / 'preparation.json'))
    m = target['manifest']
    if os.getuid() != m['control_uid']:
        raise ValueError('dedicated_control_user_required')
    activation = read_json(directory / 'activation.json')
    if (activation.get('phase') != 'DEPLOYMENT_ATTEMPTED'
            or activation.get('previous') != approved_previous or activation.get('target') != approved_candidate
            or any(activation.get(k) != v for k, v in extra.items())
            or activation.get('task_admission_resumed') is not False or activation.get('paid_calls') != 0):
        raise ValueError('planning_exact_attempted_activation_required')
    state_file = Path(m['data_root']) / 'deployment.json'
    state = read_json(state_file)
    controller = scope.controller(target, directory)
    if (state.get('bundle') != approved_candidate or state.get('revision') != m['revision']
            or Path(state.get('directory', '')).resolve() != directory.resolve()):
        raise ValueError('planning_exact_target_deployment_required')
    if state.get('phase') == 'INTENT':
        controller.reconcile_intent(approved_candidate)
    elif state.get('phase') != 'VERIFIED':
        raise ValueError('planning_target_intent_or_verified_required')
    lock = os.open(Path(m['data_root']) / 'deployment.lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        deadline(approved_until)
        state = read_json(state_file)
        if (state.get('phase') != 'VERIFIED' or state.get('bundle') != approved_candidate
                or state.get('revision') != m['revision']
                or Path(state.get('directory', '')).resolve() != directory.resolve()):
            raise ValueError('planning_verified_target_changed')
        live = connection(Path(m['data_root']) / 'telegram/connection.json')
        controller.preflight()
        checks = controller.postcheck()
        deadline(approved_until)
        scope.validate(previous, target, directory, read_json(directory / 'preparation.json'))
        if (read_json(state_file) != state or read_json(directory / 'activation.json') != activation
                or connection(Path(m['data_root']) / 'telegram/connection.json') != live
                or digest(live.model_dump()) != m['telegram']['connection_digest']):
            raise ValueError('planning_reconciliation_evidence_changed')
        atomic_json(directory / 'activation.json', {**activation, 'phase': 'VERIFIED', 'checks': checks})
    finally:
        os.close(lock)
    return {'status': 'PLANNING_ACTIVATION_RECONCILED', 'candidate_bundle': approved_candidate,
            'runtime_changed': False, 'binding_changed': False, 'task_admission_resumed': False, 'paid_calls': 0}


def main():
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'invalid planning activation arguments; values not displayed\n')
    parser = SafeParser(description=__doc__)
    parser.add_argument('action', choices=['capability', 'apply', 'reconcile'])
    parser.add_argument('--candidate-directory', required=True)
    parser.add_argument('--approved-candidate', required=True)
    parser.add_argument('--previous-directory')
    parser.add_argument('--approved-previous')
    parser.add_argument('--approved-preparation')
    parser.add_argument('--approved-capability')
    parser.add_argument('--approved-until', type=int)
    args = vars(parser.parse_args())
    action = args.pop('action')
    try:
        if action == 'capability':
            bundle = load_bundle(args['candidate_directory'])
            if checksum(bundle) != args['approved_candidate']:
                raise ValueError('exact_candidate_required')
            document = capability(bundle)
            result = {'capability': document, 'capability_digest': digest(document), 'authorization_granted': False}
        else:
            if any(v is None for v in args.values()):
                raise ValueError('all_exact_approvals_required')
            result = (apply if action == 'apply' else reconcile)(**args)
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        print(json.dumps({'status': 'BLOCKED_REQUIRES_INSPECTION', 'error_type': type(error).__name__,
                          'task_admission_resumed': False, 'paid_calls': 0}, sort_keys=True))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
