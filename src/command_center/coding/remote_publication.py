"""Git Data + draft PR publication, pinned to independently verified Git objects."""
from datetime import datetime, timezone
from uuid import uuid4

from dulwich.objects import Blob, Commit

from ..store import Denied, digest
from .publication import prepare_draft
from .spec import BASE_SHA, branch_name
from .verification import inspect_result


def publication_plan(repository, task, report, objects, files):
    prefix = '/repos/' + repository
    operations = []
    for oid, obj in sorted(objects.items()):
        if isinstance(obj, Blob):
            operations.append(('blob/' + oid.decode(), prefix + '/git/blobs',
                               {'content': obj.data.decode(), 'encoding': 'utf-8'}, oid.decode()))
    for recorded in report['checks']:
        commit = objects[recorded['commit'].encode()]
        tree = objects[commit.tree]
        operations.append(('tree/' + tree.id.decode(), prefix + '/git/trees', {'tree': [
            {'path': name.decode(), 'mode': '100644', 'type': 'blob', 'sha': oid.decode()}
            for name, _, oid in tree.iteritems()]}, tree.id.decode()))
        def identity(raw, epoch):
            name, email = raw.decode().rsplit(' <', 1)
            return {'name': name, 'email': email[:-1],
                    'date': datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace('+00:00', 'Z')}
        if not isinstance(commit, Commit):
            raise Denied('invalid_publication_commit')
        operations.append(('commit/' + commit.id.decode(), prefix + '/git/commits', {
            'message': commit.message.decode(), 'tree': commit.tree.decode(),
            'parents': [p.decode() for p in commit.parents],
            'author': identity(commit.author, commit.author_time),
            'committer': identity(commit.committer, commit.commit_time)}, commit.id.decode()))
    branch = branch_name(task['id'], task['fence'])
    operations.append(('branch', prefix + '/git/refs',
                       {'ref': 'refs/heads/' + branch, 'sha': report['head_sha']}, None))
    draft = prepare_draft(task['id'], report, files)
    marker = '<!-- acc-f2:' + task['id'] + ':' + report['head_sha'] + ' -->'
    operations.append(('pull', prefix + '/pulls', {'title': draft['title'], 'body': draft['body'] + '\n' + marker,
                                                'head': branch, 'base': 'main', 'draft': True}, None))
    return operations, draft, marker


class RemotePublisher:
    def __init__(self, gateway, task):
        self.gateway, self.task = gateway, task

    def verify_repository(self):
        g, task = self.gateway, self.task
        if not g.config.first_experiment:
            return
        from .first_experiment import validate_repository, validate_repository_identity
        prefix = '/repos/' + g.config.synthetic_repository
        nonce = uuid4().hex[:8]
        metadata = g.request(task['id'], task['fence'], 'repo/' + nonce, 'github', 'GET', prefix)
        branch = g.request(task['id'], task['fence'], 'protection/' + nonce, 'github', 'GET', prefix + '/branches/main')
        validate_repository_identity(metadata, branch, g.config.synthetic_repository, g.config.first_experiment.repository_id)
        discovery = None
        if metadata.get('permissions', {}).get('push') is not True:
            from .git_capability import discovery_path
            discovery = g.request(task['id'], task['fence'], 'git-discovery/' + uuid4().hex, 'github_git', 'GET',
                                  discovery_path(g.config.synthetic_repository))
        validate_repository(metadata, branch, g.config.synthetic_repository, g.config.first_experiment.repository_id,
                            git_discovery=discovery)

    def publish(self, result):
        g, task = self.gateway, self.task
        report, objects, snapshots = inspect_result(result, task['id'], task['fence'], task['payload']['coding'])
        # The runner must have persisted a separately replayed proof before this method.
        current = g.store.get(task['id'])['coding']
        if current.get('independent_proof') != digest(report):
            raise Denied('independent_verifier_required')
        operations, draft, marker = publication_plan(g.config.synthetic_repository, task, report, objects, snapshots[-1])
        plan = {key: digest({'kind': 'github', 'method': 'POST', 'path': path, 'body': body, 'query': None})
                for key, path, body, _ in operations}
        g.store.coding_stage(task['id'], task['fence'], 'publication_pending',
                             publication_plan=plan, summary='Результат проверен. Подготовка разрешённого draft PR.')
        prefix = '/repos/' + g.config.synthetic_repository
        self.verify_repository()
        base = g.request(task['id'], task['fence'], 'base-check/' + uuid4().hex[:8], 'github', 'GET', prefix + '/git/ref/heads/main')
        if base.get('object', {}).get('sha') != BASE_SHA:
            raise Denied('remote_base_revision_changed')
        for key, path, body, expected in operations:
            # Revalidate remote base immediately before branch creation and PR creation.
            if key in {'branch', 'pull'}:
                fresh = g.request(task['id'], task['fence'], key + '/base/' + uuid4().hex[:8], 'github', 'GET',
                                  prefix + '/git/ref/heads/main')
                if fresh.get('object', {}).get('sha') != BASE_SHA:
                    raise Denied('remote_base_revision_changed')
                if key == 'pull':
                    head = g.request(task['id'], task['fence'], 'head-check/' + uuid4().hex[:8], 'github', 'GET',
                                     prefix + '/git/ref/heads/' + report['branch'])
                    if head.get('object', {}).get('sha') != report['head_sha']:
                        raise Denied('remote_head_revision_changed')
            data = g.request(task['id'], task['fence'], key, 'github', 'POST', path, body)
            if expected and data.get('sha') != expected:
                raise Denied('remote_git_object_mismatch')
            if key == 'branch' and (data.get('ref') != body['ref'] or data.get('object', {}).get('sha') != report['head_sha']):
                raise Denied('remote_branch_mismatch')
            if key == 'pull':
                self.validate_pr(data, report, marker)
                return {**draft, 'mode': 'http_mock' if g.config.mode == 'http_mock' else 'github',
                        'published': g.config.mode == 'live', 'url': data['html_url'],
                        'remote_number': data['number'], 'remote_id': data['id'],
                        'head_sha': report['head_sha'], 'mock_endpoint': g.config.mode == 'http_mock'}
        raise Denied('publication_incomplete')

    def validate_pr(self, data, report, marker):
        repo = self.gateway.config.synthetic_repository
        if (type(data.get('number')) is not int or type(data.get('id')) is not int
                or data.get('draft') is not True or data.get('state') != 'open'
                or data.get('head', {}).get('sha') != report['head_sha']
                or data.get('head', {}).get('ref') != report['branch']
                or data.get('head', {}).get('repo', {}).get('full_name') != repo
                or data.get('base', {}).get('sha') != BASE_SHA
                or data.get('base', {}).get('ref') != 'main'
                or data.get('base', {}).get('repo', {}).get('full_name') != repo
                or marker not in data.get('body', '')
                or data.get('html_url') != f'https://github.com/{repo}/pull/{data["number"]}'):
            raise Denied('remote_pull_request_mismatch')

    def reconcile(self, result):
        """Only reads known object/branch/PR state; never repeats an uncertain POST."""
        from sqlalchemy import select
        from ..models import ExternalAction
        g, task = self.gateway, self.task
        report, objects, snapshots = inspect_result(result, task['id'], task['fence'], task['payload']['coding'])
        operations, _, marker = publication_plan(g.config.synthetic_repository, task, report, objects, snapshots[-1])
        prefix = '/repos/' + g.config.synthetic_repository
        for key, path, body, expected in operations:
            with g.store.transaction() as s:
                g.authority(s, task['id'], task['fence'])
                row = s.execute(select(ExternalAction).where(ExternalAction.key == task['id'] + ':' + key)).scalar_one_or_none()
                if not row or row.state == 'COMPLETE':
                    continue
                request_hash = row.request_hash
            if expected:
                data = g.request(task['id'], task['fence'], 'read/' + key + '/' + uuid4().hex[:8], 'github', 'GET', path + '/' + expected, reconcile=True)
                if data.get('sha') != expected:
                    raise Denied('remote_reconciliation_mismatch')
            elif key == 'branch':
                data = g.request(task['id'], task['fence'], 'read/branch/' + uuid4().hex[:8], 'github', 'GET',
                                 prefix + '/git/ref/heads/' + report['branch'], reconcile=True)
                if data.get('object', {}).get('sha') != report['head_sha']:
                    raise Denied('remote_reconciliation_mismatch')
            else:
                data = g.request(task['id'], task['fence'], 'read/pull/' + uuid4().hex[:8], 'github', 'GET', prefix + '/pulls',
                                 query={'head': g.config.synthetic_repository.split('/')[0] + ':' + report['branch'],
                                        'base': 'main', 'state': 'open'}, reconcile=True)
                if not isinstance(data, list) or len(data) != 1:
                    raise Denied('remote_publication_still_uncertain')
                data = data[0]
                self.validate_pr(data, report, marker)
            g.resolve_read_evidence(task['id'], task['fence'], key, request_hash, data)
