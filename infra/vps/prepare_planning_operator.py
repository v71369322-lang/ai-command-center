#!/usr/bin/env python3
"""Offline operator input/template/profile conversion. No credential, API or deployment action."""
import argparse
import json

from command_center.planning_operator import template, inspect_input, prepare, inspect_profile


def main():
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'invalid operator profile arguments; values not displayed\n')
    parser = SafeParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True, parser_class=SafeParser)
    actions.add_parser('template')
    check = actions.add_parser('check-input')
    check.add_argument('--input-file', required=True)
    create = actions.add_parser('prepare')
    create.add_argument('--input-file', required=True)
    create.add_argument('--approved-input', required=True)
    create.add_argument('--output', required=True)
    verify = actions.add_parser('inspect')
    verify.add_argument('--directory', required=True)
    verify.add_argument('--approved-creation', required=True)
    args = parser.parse_args()
    try:
        if args.action == 'template':
            result = template()
        elif args.action == 'check-input':
            result = inspect_input(args.input_file)
        elif args.action == 'prepare':
            result = prepare(args.input_file, args.approved_input, args.output)
        else:
            result = inspect_profile(args.directory, args.approved_creation)
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        print(json.dumps({'status': 'BLOCKED_REQUIRES_REVIEWED_INPUT', 'error_type': type(error).__name__,
                          'paid_calls_authorized': False}, sort_keys=True))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
