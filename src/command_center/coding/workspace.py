"""Real Git object history in a fresh private directory; no clone, remotes or hooks."""
import base64
from pathlib import Path

from dulwich.repo import Repo

from .spec import BASE_SHA, FILES, branch_name, commit_objects, safe_source


class Workspace:
    def __init__(self, root, task_id, fence, base_sha):
        if base_sha != BASE_SHA:
            raise ValueError('source_pin_changed')
        self.root = Path(root)
        if self.root.exists() or self.root.is_symlink():
            raise ValueError('workspace_must_be_fresh')
        self.root.mkdir(mode=0o700)
        self.repo = Repo.init(self.root, default_branch=b'main')
        seed = commit_objects(FILES)
        for obj in seed:
            self.repo.object_store.add_object(obj)
        self.repo.refs[b'refs/heads/main'] = seed[-1].id
        self.branch = branch_name(task_id, fence)
        self.ref = ('refs/heads/' + self.branch).encode()
        self.repo.refs[self.ref] = seed[-1].id
        self.repo.refs.set_symbolic_ref(b'HEAD', self.ref)
        self.repo.get_worktree().reset_index(seed[-1].tree)
        self.commits = []

    def check_pin(self):
        if self.repo.refs[b'refs/heads/main'].decode() != BASE_SHA:
            raise ValueError('source_pin_changed')
        if self.repo.refs.read_ref(b'HEAD') != b'ref: ' + self.ref:
            raise ValueError('workspace_branch_changed')

    def apply(self, changes):
        self.check_pin()
        if not isinstance(changes, dict) or set(changes) != {'calculator.py'}:
            raise ValueError('write_scope_violation')
        path = self.root / 'calculator.py'
        if path.is_symlink() or not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError('workspace_escape')
        safe_source(changes['calculator.py'])
        path.write_text(changes['calculator.py'])

    def commit(self):
        self.check_pin()
        files = {name: (self.root / name).read_text() for name in FILES}
        if any(files[name] != value for name, value in FILES.items() if name != 'calculator.py'):
            raise ValueError('acceptance_files_modified')
        objects = commit_objects(files, self.repo.head(), len(self.commits) + 1)
        for obj in objects:
            self.repo.object_store.add_object(obj)
        self.repo.refs[self.ref] = objects[-1].id
        self.repo.get_worktree().reset_index(objects[-1].tree)
        self.commits.append(objects[-1].id.decode())
        return self.commits[-1]

    def export(self):
        self.check_pin()
        return {'base_sha': BASE_SHA, 'branch': self.branch, 'head_sha': self.repo.head().decode(),
                'commits': self.commits,
                'objects': {oid.decode(): {'type': self.repo.object_store[oid].type_num,
                                          'data': base64.b64encode(self.repo.object_store[oid].as_raw_string()).decode()}
                            for oid in sorted(self.repo.object_store)}}
