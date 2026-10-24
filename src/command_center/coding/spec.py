"""Owner-visible fixed synthetic acceptance contract, not agent-authored tests."""
import ast
import re
from uuid import UUID

from dulwich.objects import Blob, Commit, Tree

REPOSITORY = 'f2-synthetic-sum'
OBJECTIVE = 'sum_positive_v1'
INITIAL = 'def sum_positive(values):\n    raise NotImplementedError("synthetic exercise")\n'
FIRST = 'def sum_positive(values):\n    return sum(values)\n'
CORRECT = 'def sum_positive(values):\n    return sum(value for value in values if value > 0)\n'
TEST_SOURCE = '''import unittest
from calculator import sum_positive
class Acceptance(unittest.TestCase):
    def test_empty(self): self.assertEqual(sum_positive([]), 0)
    def test_positive(self): self.assertEqual(sum_positive([1, 2, 3]), 6)
    def test_mixed(self): self.assertEqual(sum_positive([-4, 2, -1, 5, 0]), 7)
    def test_negative(self): self.assertEqual(sum_positive([0, -8]), 0)
'''
FILES = {'calculator.py': INITIAL, 'test_calculator.py': TEST_SOURCE,
         'README.md': '# Synthetic F2 exercise\nOnly calculator.py may change. No remote repository.\n'}
PLAN = ['Создать отдельную ветку тестового репозитория', 'Исправить функцию и запустить проверки',
        'Исправить найденную ошибку в пределах лимита', 'Независимо перепроверить и подготовить PR']


def commit_objects(files, parent=None, ordinal=0):
    objects = []
    tree = Tree()
    for name, content in sorted(files.items()):
        blob = Blob.from_string(content.encode())
        objects.append(blob)
        tree.add(name.encode(), 0o100644, blob.id)
    commit = Commit()
    commit.tree = tree.id
    commit.parents = [parent] if parent else []
    commit.author = commit.committer = b'F2 synthetic fixture <fixture@invalid>'
    commit.author_time = commit.commit_time = ordinal
    commit.author_timezone = commit.commit_timezone = 0
    commit.message = b'Synthetic baseline\n' if ordinal == 0 else f'Coding attempt {ordinal}\n'.encode()
    return [*objects, tree, commit]


BASE_SHA = commit_objects(FILES)[-1].id.decode()


def branch_name(task_id, fence):
    if type(fence) is not int or fence < 1:
        raise ValueError('invalid_fence')
    return f'f2/task-{UUID(task_id)}-{fence}'


def safe_source(source, allow_initial=False):
    if not isinstance(source, str) or len(source.encode()) > 4096:
        raise ValueError('source_size_limit')
    allowed = [FIRST, CORRECT] + ([INITIAL] if allow_initial else [])
    parsed = ast.dump(ast.parse(source), include_attributes=False)
    if parsed not in {ast.dump(ast.parse(item), include_attributes=False) for item in allowed}:
        raise ValueError('synthetic_language_scope_violation')
    if re.search(r'-----BEGIN .*PRIVATE KEY|\b(?:sk-|ghp_)[A-Za-z0-9_-]{20,}', source):
        raise ValueError('possible_secret')
    return parsed
