"""Offline input materializer: exact Git objects/replacements, no grants or network."""
import argparse
import base64
import json
import os
from pathlib import Path

from dulwich.repo import Repo

from command_center.coding_preparation import CodingScope
from command_center.isolated_coding import Snapshot, validate_payload
from command_center.store import canonical, digest


def materialize(repository, preparation, replacements):
    spec = preparation['specification']
    if digest(spec) != preparation['spec_digest']:
        raise ValueError('specification_digest_mismatch')
    scope = CodingScope.model_validate(spec['scope'])
    revision = spec['acceptance_reference']['declared_repository_revision']
    with Repo(repository) as repo:
        # Read object database only. Working-tree edits, hooks and remotes are unused.
        commit = repo[revision.encode()]
        selected = {commit.id: commit}
        for path in sorted(set([*scope.allowed_files, *scope.test_files])):
            oid = commit.tree
            for part in path.split('/'):
                tree = repo[oid]
                selected[tree.id] = tree
                _, oid = tree[part.encode()]
            blob = repo[oid]
            selected[blob.id] = blob
    snapshot = Snapshot(objects=[{'kind': obj.type_name.decode(),
        'data': base64.b64encode(obj.as_raw_string()).decode()} for obj in selected.values()]).model_dump()
    snapshot['objects'].sort(key=canonical)
    payload = {'kind': 'isolated_coding', 'spec_digest': preparation['spec_digest'],
               'specification': spec, 'snapshot': snapshot, 'replacements': replacements, 'cost': 0}
    validate_payload(payload)
    return {'request_id': spec['acceptance_reference']['request_id'],
            'expected_spec_digest': preparation['spec_digest'], 'snapshot': snapshot, 'replacements': replacements}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--preparation', required=True, help='Saved preparation JSON; no credentials')
    parser.add_argument('--replacements', required=True, help='Explicit JSON mapping from path to full new source')
    parser.add_argument('--output', required=True, help='New operator-controlled private file, never Git')
    args = parser.parse_args()
    value = materialize(args.repository, json.loads(Path(args.preparation).read_text(encoding='utf-8')),
                        json.loads(Path(args.replacements).read_text(encoding='utf-8')))
    # Exclusive creation: never follow/overwrite an existing output or symlink.
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as output:
        json.dump(value, output, ensure_ascii=True, sort_keys=True)
        output.write('\n')
    print('Offline binding input prepared; no task, approval, remote access or execution.')


if __name__ == '__main__':
    main()
