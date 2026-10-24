"""PR drafts contain verified evidence; no GitHub credential reaches an executor."""
import difflib
import hashlib
import re
from urllib.parse import quote

import httpx

from .spec import FILES


def prepare_draft(task_id, report, final_files):
    if report.get('passed') is not True:
        raise ValueError('unverified_result_cannot_publish')
    diff = ''.join(difflib.unified_diff(FILES['calculator.py'].splitlines(True),
                                      final_files['calculator.py'].splitlines(True),
                                      fromfile='a/calculator.py', tofile='b/calculator.py'))
    key = hashlib.sha256((task_id + report['head_sha']).encode()).hexdigest()
    return {'mode': 'mock', 'published': False, 'idempotency_key': key,
            'title': 'Исправлена сумма положительных чисел в тестовом репозитории',
            'task_id': task_id, 'task_link': '/#task-' + task_id,
            'base_branch': 'main', 'base_sha': report['base_sha'], 'head_sha': report['head_sha'],
            'head_branch': report['branch'], 'checks': report['checks'],
            'risks': ['Только синтетический репозиторий; реальный AI и GitHub publication не проверены'],
            'unverified': ['real provider', 'remote branch publication', 'production isolation'],
            'diff': diff, 'body': ('Synthetic task /#task-' + task_id + '\nChanged: calculator.py\nBase: '
                                  + report['base_sha'] + '\nHead: ' + report['head_sha']
                                  + '\nIndependent replay: 4 acceptance tests per commit; final PASS.'
                                  + '\nUnverified: real AI, remote publishing, production isolation.'
                                  + '\nLow risk only within the synthetic fixture. No automatic merge.'),
            'url': None}


class PublicationUncertain(RuntimeError):
    pass


class GitHubPublisher:
    """Official REST adapter, dormant in F2. Journal MUST be durable before real use.
    Requires a separately authorized synthetic remote branch already at head_sha.
    Tests use MockTransport + a synthetic journal; no real requests or credentials.
    """
    def __init__(self, repository, token, *, authorized=False, client=None):
        if not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+', repository):
            raise ValueError('repository_allowlist_required')
        self.repository, self.token, self.authorized, self.client = repository, token, authorized, client

    def publish(self, draft, journal):
        if not self.authorized or not self.token or draft.get('mode') != 'mock':
            raise PermissionError('github_publication_not_authorized')
        if not re.fullmatch(r'f2/task-[a-f0-9-]{36}-[1-9][0-9]*', draft['head_branch']):
            raise ValueError('branch_scope_violation')
        key = draft['idempotency_key']
        if journal.get(key) is not None:
            raise PublicationUncertain('reconcile_existing_intent_before_retry')
        client = self.client or httpx.Client(follow_redirects=False)
        root = 'https://api.github.com/repos/' + self.repository
        headers = {'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json'}
        try:
            for ref, expected in [(draft['base_branch'], draft['base_sha']), (draft['head_branch'], draft['head_sha'])]:
                response = client.get(root + '/git/ref/heads/' + quote(ref, safe='/'), headers=headers, timeout=5, follow_redirects=False)
                if response.status_code != 200 or response.json()['object']['sha'] != expected:
                    raise ValueError('remote_revision_mismatch')
            # Caller supplies a durable PG-backed journal in a future authorized integration.
            journal[key] = {'state': 'INTENT', 'head_sha': draft['head_sha']}
            response = client.post(root + '/pulls', headers=headers, timeout=10, follow_redirects=False,
                                   json={'title': draft['title'], 'body': draft['body'],
                                         'head': draft['head_branch'], 'base': draft['base_branch'], 'draft': True})
            if response.status_code != 201:
                raise PublicationUncertain('publication_outcome_requires_reconciliation')
            result = response.json()
            journal[key] = {'state': 'PUBLISHED', 'number': result['number'], 'url': result['html_url']}
            return journal[key]
        except httpx.RequestError:
            raise PublicationUncertain('publication_outcome_requires_reconciliation') from None
        finally:
            if self.client is None:
                client.close()
