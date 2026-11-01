"""Offline synthetic Git seed. Never creates a remote or obtains credentials."""
import argparse
import json

from .spec import BASE_SHA, FILES
from .workspace import Workspace


def prepare(path):
    workspace = Workspace(path, '00000000-0000-4000-8000-000000000022', 1, BASE_SHA)
    try:
        workspace.repo.refs.set_symbolic_ref(b'HEAD', b'refs/heads/main')
        workspace.repo.refs.remove_if_equals(workspace.ref, BASE_SHA.encode())
        return {'base_sha': workspace.repo.head().decode(), 'files': sorted(FILES), 'remote_configured': False}
    finally:
        workspace.repo.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    args = parser.parse_args()
    print(json.dumps(prepare(args.directory)))


if __name__ == '__main__':
    main()
