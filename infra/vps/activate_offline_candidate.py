#!/usr/bin/env python3
"""Restriction-only adapter over the existing planning/Telegram deployment transaction."""
import argparse
import json

from command_center.offline_candidate import PURPOSE, inspect, prepare
from command_center.store import digest
from activate_planning_candidate import PlanningUpdate, reconcile as reconcile_transition
from apply_reconciled_telegram_candidate import apply as apply_transition


class OfflineUpdate(PlanningUpdate):
    def postcheck(self):
        result = super().postcheck()
        result.pop('planning_runtime_ready')
        self.engine.run('exec', 'acc-f23-runtime-broker-1', 'python', '-c',
            'import os;from command_center.code_generation import configured;'
            'from command_center.config import Settings;from command_center.store import Store;'
            's=Store(Settings.load(identities_required=False));'
            'assert not any(k.startswith("F1_PLANNING_") or k.startswith("F2_INTEGRATION_") for k in os.environ);'
            'exec("with s.transaction() as tx:\\n p,_=configured(s,tx);assert not p.connected()")')
        return {**result, 'offline_runtime_ready': True, 'provider_bindings_removed': True}


class OfflineScope:
    def __init__(self, previous, candidate, preparation):
        self.previous, self.candidate, self.preparation = previous, candidate, preparation

    def validate(self, previous, target, directory, receipt):
        inspect(directory, self.candidate, self.preparation)
        if (receipt['previous_bundle'] != self.previous or receipt['candidate_bundle'] != self.candidate
                or digest(previous) != self.previous or digest(target) != self.candidate
                or receipt['purpose'] != PURPOSE):
            raise ValueError('offline_exact_transition_required')
        return {'purpose': PURPOSE, 'preparation_digest': self.preparation, 'provider_bindings_removed': True}

    @staticmethod
    def controller(target, directory):
        return OfflineUpdate(target, directory)


def activate(previous_directory, candidate_directory, approved_previous, approved_candidate,
             approved_preparation, approved_until, *, reconcile=False):
    scope = OfflineScope(approved_previous, approved_candidate, approved_preparation)
    if reconcile:
        result = reconcile_transition(previous_directory, candidate_directory, approved_previous,
            approved_candidate, approved_until, approved_preparation, None, _scope=scope)
    else:
        result = apply_transition(previous_directory, candidate_directory, approved_previous,
                                  approved_candidate, approved_until, _planning=scope)
    return {**result, 'status': 'OFFLINE_ACTIVATION_RECONCILED' if reconcile else 'OFFLINE_CANDIDATE_APPLIED',
            'provider_bindings_removed': True}


def main():
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'invalid offline release arguments; values not displayed\n')
    parser = SafeParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True, parser_class=SafeParser)
    p = actions.add_parser('prepare')
    for k in ('previous-directory', 'disabled-directory', 'output', 'previous-pin', 'disabled-pin'):
        p.add_argument('--' + k, required=True)
    p = actions.add_parser('inspect')
    for k in ('directory', 'candidate-pin', 'preparation-pin'):
        p.add_argument('--' + k, required=True)
    for action in ('apply', 'reconcile'):
        p = actions.add_parser(action)
        for k in ('previous-directory', 'candidate-directory', 'approved-previous', 'approved-candidate',
                  'approved-preparation'):
            p.add_argument('--' + k, required=True)
        p.add_argument('--approved-until', type=int, required=True)
    args = vars(parser.parse_args())
    action = args.pop('action')
    try:
        result = prepare(**args) if action == 'prepare' else inspect(**args) if action == 'inspect' else activate(
            **args, reconcile=action == 'reconcile')
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        print(json.dumps({'status': 'BLOCKED_REQUIRES_INSPECTION', 'error_type': type(error).__name__, 'paid_calls': 0}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
