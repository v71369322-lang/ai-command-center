#!/usr/bin/env python3
"""Prepare or verify an offline planning review package. No apply command exists."""
import argparse
import json

from command_center.planning_release import prepare, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    create = actions.add_parser('prepare')
    for name in ('previous', 'candidate', 'output', 'previous-pin', 'candidate-pin'):
        create.add_argument('--' + name, required=True)
    check = actions.add_parser('verify')
    check.add_argument('--directory', required=True)
    check.add_argument('--seal', required=True)
    args = parser.parse_args()
    if args.action == 'prepare':
        result = {'seal': prepare(args.previous, args.candidate, args.output,
                                 args.previous_pin, args.candidate_pin),
                  'status': 'BLOCKED_NOT_ACTIVATABLE'}
    else:
        result = verify(args.directory, args.seal)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
