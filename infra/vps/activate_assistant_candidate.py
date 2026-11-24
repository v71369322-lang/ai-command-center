#!/usr/bin/env python3
"""Exact restriction-only Jarvis cutover through existing activation journals."""
import argparse
import json

from command_center.assistant_candidate import PURPOSE, inspect, prepare, prepare_profile
from command_center.deployment import Deployment
from command_center.deployment_profile import checksum
from command_center.deployment_voice import heartbeat_check_code
from command_center.maintenance_admission import entry_retry_code
from command_center.planning_candidate import read_json
from activate_planning_candidate import reconcile as reconcile_transition
from apply_reconciled_telegram_candidate import ReconciledUpdate, apply as apply_transition


class PreviousUpdate(Deployment):
    def tool(self, code):
        if self.m.get('assistant_only'):
            # Deployment.tool already adds this wrapper for assistant releases.
            # Applying it twice makes the embedded global original reference
            # point at the wrapper itself and recursively re-enter it.
            return super().tool(code)
        return super().tool(entry_retry_code() + code)


class AssistantUpdate(ReconciledUpdate):
    def postcheck(self):
        result = super().postcheck()
        self.tool('''from sqlalchemy import select
from command_center.config import Settings
from command_center.store import Store
from command_center.models import ExternalAction
from command_center.coding.gateway import Gateway
s=Store(Settings.load())
s.checkpoint()
state=s.snapshot()
assert state['halted'] and not state['recovery'] and state['budget']['uncertain']==0
assert all(t['state'] not in {'RUNNING','CANCEL_REQUESTED','RECONCILING'} for t in state['tasks'])
with s.transaction() as tx:
    rows=list(tx.scalars(select(ExternalAction)))
    Gateway.check_ledger(tx,rows)
    assert all(row.state=='COMPLETE' and row.reserved==0 for row in rows)
''')
        self.tool(heartbeat_check_code(self.m))
        return {**result, 'state': 'ASSISTANT_ONLY_SERVICES_RUNNING', 'admission_halted': True,
                'developer_services_stopped': True, 'financial_ledger_verified': True,
                'paid_calls_authorized': False}


class AssistantScope:
    assistant_only = True

    def __init__(self, previous, candidate, preparation):
        self.previous, self.candidate, self.preparation = previous, candidate, preparation

    def validate(self, previous, target, directory, receipt):
        inspect(directory, self.candidate, self.preparation)
        if (receipt['purpose'] != PURPOSE or receipt['previous_bundle'] != self.previous
                or checksum(previous) != self.previous or checksum(target) != self.candidate):
            raise ValueError('assistant_exact_transition_approval_required')
        return {'purpose': PURPOSE, 'preparation_digest': self.preparation}

    @staticmethod
    def controller(target, directory):
        return AssistantUpdate(target, directory)

    @staticmethod
    def predecessor_controller(previous, directory):
        return PreviousUpdate(previous, directory)


def activate(previous_directory, candidate_directory, approved_previous, approved_candidate,
             approved_preparation, approved_until, *, reconcile=False):
    scope = AssistantScope(approved_previous, approved_candidate, approved_preparation)
    if reconcile:
        result = reconcile_transition(previous_directory, candidate_directory, approved_previous,
            approved_candidate, approved_until, approved_preparation, None, _scope=scope)
    else:
        result = apply_transition(previous_directory, candidate_directory, approved_previous,
            approved_candidate, approved_until, _planning=scope)
    return {**result, 'status': 'ASSISTANT_ACTIVATION_RECONCILED' if reconcile else 'ASSISTANT_CANDIDATE_APPLIED'}


def main():
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'invalid assistant release arguments; values not displayed\n')
    parser = SafeParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True, parser_class=SafeParser)
    p = actions.add_parser('profile')
    for key in ('previous-directory', 'plain-directory', 'profile-directory', 'image'):
        p.add_argument('--' + key, required=True)
    p = actions.add_parser('prepare')
    for key in ('previous-directory', 'plain-directory', 'output', 'voice-binding-file', 'previous-pin', 'plain-pin'):
        p.add_argument('--' + key, required=True)
    p.add_argument('--calendar-binding-file')
    p.add_argument('--telegram-cpu', type=int, choices=(1,))
    p = actions.add_parser('inspect')
    for key in ('directory', 'candidate-pin', 'preparation-pin'):
        p.add_argument('--' + key, required=True)
    for action in ('apply', 'reconcile'):
        p = actions.add_parser(action)
        for key in ('previous-directory', 'candidate-directory', 'approved-previous', 'approved-candidate',
                    'approved-preparation'):
            p.add_argument('--' + key, required=True)
        p.add_argument('--approved-until', type=int, required=True)
    args = vars(parser.parse_args())
    action = args.pop('action')
    try:
        if action == 'profile':
            result = prepare_profile(**args)
        elif action == 'prepare':
            calendar_file = args.pop('calendar_binding_file')
            if calendar_file:
                args['calendar'] = read_json(calendar_file)
            args['voice'] = read_json(args.pop('voice_binding_file'))
            result = prepare(**args)
        elif action == 'inspect':
            result = inspect(**args)
        else:
            result = activate(**args, reconcile=action == 'reconcile')
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        print(json.dumps({'status': 'BLOCKED_REQUIRES_INSPECTION', 'error_type': type(error).__name__, 'paid_calls': 0}))
        parser.exit(1)


if __name__ == '__main__':
    main()
