"""Offline repository-slice jobs on F1. No fetch, AI, publisher or host workspace."""
import base64
import difflib
import hashlib
from typing import Literal

from dulwich.objects import Blob, Commit, Tree
from dulwich.errors import FileFormatException
from pydantic import Field

from .coding_preparation import CodingScope, history, read_locked
from .project_inbox import check_content, owner
from .request_planning import HEX, REQUEST, Strict
from .store import Denied, canonical, digest

KIND = 'isolated_coding'
MAX_BYTES = 48000


class GitObject(Strict):
    kind: Literal['commit', 'tree', 'blob']
    data: str = Field(max_length=48000)


class Snapshot(Strict):
    objects: list[GitObject] = Field(min_length=3, max_length=64)


class BindRequest(Strict):
    request_id: str = Field(pattern=REQUEST)
    expected_spec_digest: str = Field(pattern=HEX)
    snapshot: Snapshot
    replacements: dict[str, str] = Field(min_length=1, max_length=8)


class BindSave(BindRequest):
    expected_payload_digest: str = Field(pattern=HEX)


def snapshot_files(snapshot, revision, paths):
    """Prove selected regular-file bytes through exact Git commit/tree/blob hashes.

    This proves content identity, not remote repository membership or permission.
    No archive extraction, symlink following, Git hooks or remote operations.
    """
    try:
        snapshot = Snapshot.model_validate(snapshot)
        if len(canonical(snapshot.model_dump()).encode()) > MAX_BYTES:
            raise ValueError()
        objects = {}
        for item in snapshot.objects:
            raw = base64.b64decode(item.data, validate=True)
            obj = {'commit': Commit, 'tree': Tree, 'blob': Blob}[item.kind].from_string(raw)
            if obj.id in objects:
                raise ValueError()
            objects[obj.id] = obj
        commit = objects[revision.encode()]
        if not isinstance(commit, Commit):
            raise ValueError()
        used, files = {commit.id}, {}
        for path in sorted(set(paths)):
            tree_id = commit.tree
            parts = path.split('/')
            for i, part in enumerate(parts):
                tree = objects[tree_id]
                if not isinstance(tree, Tree):
                    raise ValueError()
                used.add(tree.id)
                mode, oid = tree[part.encode()]
                if i < len(parts) - 1:
                    if mode != 0o040000:
                        raise ValueError()
                    tree_id = oid
                else:
                    blob = objects[oid]
                    if mode != 0o100644 or not isinstance(blob, Blob):
                        raise ValueError()
                    used.add(blob.id)
                    files[path] = blob.data.decode('utf-8')
        if used != set(objects):
            raise ValueError()
        return files
    except (ValueError, KeyError, TypeError, UnicodeError, AttributeError, IndexError, FileFormatException):
        raise Denied('coding_snapshot_invalid') from None


def validate_payload(value):
    from .coding_preparation import specification
    from .plan_acceptance import Reference
    try:
        if (set(value) != {'kind', 'spec_digest', 'specification', 'snapshot', 'replacements', 'cost'}
                or value['kind'] != KIND or type(value['cost']) is not int or value['cost'] != 0
                or len(canonical(value).encode()) > MAX_BYTES):
            raise ValueError()
        spec = value['specification']
        if value['snapshot']['objects'] != sorted(value['snapshot']['objects'], key=canonical):
            raise ValueError()
        ref = Reference.model_validate(spec['acceptance_reference']).model_dump()
        scope = CodingScope.model_validate(spec['scope'])
        if canonical(spec) != canonical(specification(ref, scope)) or digest(spec) != value['spec_digest']:
            raise ValueError()
        files = snapshot_files(value['snapshot'], ref['declared_repository_revision'],
                               [*scope.allowed_files, *scope.test_files])
        replacements = value['replacements']
        if (not isinstance(replacements, dict) or not 1 <= len(replacements) <= 8
                or not set(replacements) <= set(scope.allowed_files)
                or any(p.startswith('tests/') for p in replacements)
                or any(not isinstance(v, str) or '\x00' in v for v in replacements.values())
                or any(v and not v.endswith('\n') for v in [*files.values(), *replacements.values()])
                or all(files[p] == v for p, v in replacements.items())):
            raise ValueError()
        patch = ''.join(''.join(difflib.unified_diff(files[p].splitlines(True), replacements[p].splitlines(True),
                        fromfile='a/' + p, tofile='b/' + p)) for p in sorted(replacements))
        if len(patch.encode()) > scope.max_diff_bytes:
            raise ValueError()
        return files, patch
    except (ValueError, KeyError, TypeError):
        raise Denied('isolated_coding_scope_invalid') from None


def check_binding(store, session, value):
    files, patch = validate_payload(value)
    pin = value['spec_digest']
    spec = value['specification']
    current = read_locked(store, session, spec['acceptance_reference']['request_id'])
    if (current['state'] != 'PREPARED_NOT_RUNNABLE'
            or current['preparation']['spec_digest'] != pin
            or canonical(current['preparation']['specification']) != canonical(spec)
            or spec['acceptance_reference']['source_revision'] != store.settings.source_revision):
        raise Denied('coding_binding_stale')
    for content in [*files.values(), *value['replacements'].values(), patch]:
        check_content(store, content)


def preview(store, role, request):
    owner(role)
    request = BindRequest.model_validate(request)
    with store.transaction() as session:
        store.check_audit(session)
        records = history(store, session)
        if request.expected_spec_digest not in records:
            raise Denied('coding_preparation_missing')
        spec = records[request.expected_spec_digest]['specification']
        if spec['acceptance_reference']['request_id'] != request.request_id:
            raise Denied('coding_request_mismatch')
        value = {'kind': KIND, 'spec_digest': request.expected_spec_digest, 'specification': spec,
                 'snapshot': {'objects': sorted(request.snapshot.model_dump()['objects'], key=canonical)},
                 'replacements': request.replacements, 'cost': 0}
        check_binding(store, session, value)
        return {'payload': value, 'payload_digest': digest(value), 'state': 'PREVIEW',
                'remote_repository_verified': False, 'paid_calls_authorized': False,
                'publication_authorized': False, 'execution_authorized': False}


def create(store, role, request):
    owner(role)
    request = BindSave.model_validate(request)
    view = preview(store, role, request.model_dump(exclude={'expected_payload_digest'}))
    if view['payload_digest'] != request.expected_payload_digest:
        raise Denied('coding_payload_changed')
    # Store revalidates the current specification under its own admission lock.
    return store.create(role, 'isolated-coding-v1:' + view['payload_digest'], view['payload'])


def report(value):
    files, patch = validate_payload(value)
    final = {**files, **value['replacements']}
    return {'spec_digest': value['spec_digest'], 'payload_digest': digest(value),
            'files': {p: hashlib.sha256(v.encode()).hexdigest() for p, v in sorted(final.items())},
            'patch': patch, 'provider_called': False, 'publication_performed': False,
            'remote_repository_verified': False}
