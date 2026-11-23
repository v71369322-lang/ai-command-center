#!/usr/bin/env python3
"""First offline voice activation over the existing exact deployment transaction."""
import argparse
import json

from command_center.voice_candidate import PURPOSE, inspect, prepare, prepare_profile
from command_center.planning_candidate import read_json
from command_center.store import digest
from activate_planning_candidate import PlanningUpdate, reconcile as reconcile_transition
from apply_reconciled_telegram_candidate import apply as apply_transition


class VoiceUpdate(PlanningUpdate):
    def postcheck(self):
        result = super().postcheck()
        result.pop('planning_runtime_ready')
        from command_center.deployment_voice import heartbeat_check_code
        self.tool(heartbeat_check_code(self.m))
        return {**result, 'offline_voice_runtime_ready': True}


class VoiceScope:
    def __init__(self, previous, candidate, preparation, capability):
        self.previous, self.candidate = previous, candidate
        self.preparation, self.capability = preparation, capability

    def validate(self, previous, target, directory, receipt):
        inspect(directory, self.candidate, self.preparation)
        if (receipt['purpose'] != PURPOSE or receipt['previous_bundle'] != self.previous
                or receipt['candidate_bundle'] != self.candidate or digest(previous) != self.previous
                or digest(target) != self.candidate or digest(target['manifest']['voice']) != self.capability
                or receipt['voice_capability'] != self.capability):
            raise ValueError('voice_exact_transition_and_access_approval_required')
        return {'purpose': PURPOSE, 'preparation_digest': self.preparation,
                'voice_capability': self.capability}

    @staticmethod
    def controller(target, directory):
        return VoiceUpdate(target, directory)


def activate(previous_directory, candidate_directory, approved_previous, approved_candidate,
             approved_preparation, approved_capability, approved_until, *, reconcile=False):
    scope = VoiceScope(approved_previous, approved_candidate, approved_preparation, approved_capability)
    if reconcile:
        result = reconcile_transition(previous_directory, candidate_directory, approved_previous,
            approved_candidate, approved_until, approved_preparation, None, _scope=scope)
    else:
        result = apply_transition(previous_directory, candidate_directory, approved_previous,
            approved_candidate, approved_until, _planning=scope)
    return {**result, 'status': 'VOICE_ACTIVATION_RECONCILED' if reconcile else 'VOICE_CANDIDATE_APPLIED'}


def main():
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'invalid voice release arguments; values not displayed\n')
    parser = SafeParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True, parser_class=SafeParser)
    p = actions.add_parser('profile')
    for key in ('previous-directory', 'plain-directory', 'profile-directory', 'model-directory',
                'image', 'since', 'model-manifest-file'):
        p.add_argument('--' + key, required=True)
    p = actions.add_parser('prepare')
    for key in ('previous-directory', 'plain-directory', 'output', 'voice-binding-file', 'previous-pin', 'plain-pin'):
        p.add_argument('--' + key, required=True)
    p = actions.add_parser('inspect')
    for key in ('directory', 'candidate-pin', 'preparation-pin'):
        p.add_argument('--' + key, required=True)
    for action in ('apply', 'reconcile'):
        p = actions.add_parser(action)
        for key in ('previous-directory', 'candidate-directory', 'approved-previous', 'approved-candidate',
                    'approved-preparation', 'approved-capability'):
            p.add_argument('--' + key, required=True)
        p.add_argument('--approved-until', type=int, required=True)
    args = vars(parser.parse_args())
    action = args.pop('action')
    try:
        if action == 'profile':
            args['model_manifest'] = read_json(args.pop('model_manifest_file'))
            result = prepare_profile(**args)
        elif action == 'prepare':
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
