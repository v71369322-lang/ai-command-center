"""Independent deterministic Git/scope checker and replay; never imports agent/provider code."""
import ast
import base64
import json
from pathlib import Path
import re
import subprocess
import sys

from dulwich.objects import Blob, Commit, ShaFile, Tree
from dulwich.repo import Repo

from .spec import BASE_SHA, CORRECT, FILES, FIRST, branch_name, commit_objects, safe_source


def inspect_result(result, task_id, fence, task):
    git = result['git']
    if (result.get('status') != 'ready_for_verification' or git['base_sha'] != BASE_SHA
            or task['base_sha'] != BASE_SHA or git['branch'] != branch_name(task_id, fence)):
        raise ValueError('git_source_or_branch_mismatch')
    if not 1 <= len(git['commits']) <= task['max_iterations'] or len(git['objects']) > 32:
        raise ValueError('git_history_limit')
    objects = {}
    total = 0
    for oid, raw in git['objects'].items():
        if not re.fullmatch('[a-f0-9]{40}', oid) or type(raw['type']) is not int or raw['type'] not in {1, 2, 3}:
            raise ValueError('invalid_git_object')
        data = base64.b64decode(raw['data'], validate=True)
        total += len(data)
        if len(data) > 8192 or total > 32768:
            raise ValueError('git_artifact_size_limit')
        obj = ShaFile.from_raw_string(raw['type'], data)
        if obj.id.decode() != oid:
            raise ValueError('git_object_checksum_mismatch')
        objects[obj.id] = obj
    reachable = set()
    for expected in commit_objects(FILES):
        reachable.add(expected.id)
        if expected.id not in objects or objects[expected.id].as_raw_string() != expected.as_raw_string():
            raise ValueError('baseline_object_missing_or_changed')
    parent = BASE_SHA
    replays = []
    snapshots = []
    for index, commit_id in enumerate(git['commits'], 1):
        commit = objects[commit_id.encode()]
        if not isinstance(commit, Commit) or commit.parents != [parent.encode()]:
            raise ValueError('nonlinear_or_unpinned_history')
        tree = objects[commit.tree]
        if not isinstance(tree, Tree):
            raise ValueError('invalid_git_tree')
        reachable.update((commit.id, tree.id))
        files = {}
        for name, mode, oid in tree.iteritems():
            if mode != 0o100644 or name.decode() not in FILES or not isinstance(objects[oid], Blob):
                raise ValueError('forbidden_path_mode_or_submodule')
            files[name.decode()] = objects[oid].data.decode()
            reachable.add(oid)
        if set(files) != set(FILES) or any(files[n] != s for n, s in FILES.items() if n != 'calculator.py'):
            raise ValueError('acceptance_or_scope_modified')
        parsed = safe_source(files['calculator.py'])
        correct = parsed == ast.dump(ast.parse(CORRECT), include_attributes=False)
        known_first = parsed == ast.dump(ast.parse(FIRST), include_attributes=False)
        if not (correct or known_first):
            raise ValueError('unverified_language')
        expected_checks = {'tests_run': 4, 'failures': 0 if correct else 2, 'errors': 0, 'passed': correct}
        record = {'attempt': index, 'commit': commit_id, 'checks': expected_checks}
        replays.append(record)
        snapshots.append(files)
        parent = commit_id
    if (set(objects) != reachable or git['head_sha'] != parent or not replays[-1]['checks']['passed'] or result['history'] != replays
            or result['usage']['synthetic'] is not True or result['usage']['units'] != len(replays)
            or type(result['usage']['units']) is not int or type(result['usage']['tokens']) is not int
            or result['usage']['units'] > task['max_units'] or not 0 <= result['usage']['tokens'] <= task['max_tokens']):
        raise ValueError('forged_result_or_budget_evidence')
    return {'base_sha': BASE_SHA, 'head_sha': parent, 'branch': git['branch'],
            'checks': replays, 'passed': True, 'allowed_files': ['calculator.py']}, objects, snapshots


def replay(result, task_id, fence, task, root):
    report, objects, snapshots = inspect_result(result, task_id, fence, task)
    root = Path(root)
    root.mkdir(mode=0o700)
    repo = Repo.init(root, default_branch=b'main')
    try:
        for obj in objects.values():
            repo.object_store.add_object(obj)
        repo.refs[b'refs/heads/main'] = BASE_SHA.encode()
        ref = ('refs/heads/' + report['branch']).encode()
        repo.refs.set_symbolic_ref(b'HEAD', ref)
        for recorded, _ in zip(report['checks'], snapshots, strict=True):
            repo.refs[ref] = recorded['commit'].encode()
            repo.get_worktree().reset_index(objects[recorded['commit'].encode()].tree)
            checker = Path(__file__).with_name('checks.py')
            checked = subprocess.run([sys.executable, '-I', '-B', str(checker), str(root)],
                                     capture_output=True, timeout=3)
            if checked.returncode or len(checked.stdout) > 2048 or json.loads(checked.stdout) != recorded['checks']:
                raise ValueError('independent_replay_failed')
        return report
    finally:
        repo.close()
