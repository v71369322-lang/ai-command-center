#!/usr/bin/env python3
"""Prepare/inspect a protected planning candidate; no apply, provider or SSH command."""
import argparse
import json

from command_center.planning_candidate import prepare, inspect


def main():
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'invalid planning candidate arguments; values not displayed\n')
    parser = SafeParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True, parser_class=SafeParser)
    create = actions.add_parser('prepare')
    for name in ('previous-directory', 'disabled-directory', 'output', 'operator-file', 'operator-pin',
                 'key-directory', 'credential-sha256', 'previous-pin', 'disabled-pin'):
        create.add_argument('--' + name, required=True)
    check = actions.add_parser('inspect')
    for name in ('directory', 'candidate-pin', 'preparation-pin'):
        check.add_argument('--' + name, required=True)
    args = vars(parser.parse_args())
    action = args.pop('action')
    try:
        print(json.dumps((prepare if action == 'prepare' else inspect)(**args), sort_keys=True))
    except Exception as error:
        print(json.dumps({'status': 'BLOCKED_REQUIRES_INSPECTION', 'error_type': type(error).__name__,
                          'deployment_authorized': False, 'paid_calls': 0}, sort_keys=True))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
