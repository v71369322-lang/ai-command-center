"""Contract HTTP fixture. No DNS, sockets, real credentials, models or tariffs."""
from datetime import datetime
import json

from dulwich.objects import Blob, Commit, Tree
import httpx

from command_center.coding.http_contract import FORMAT, INSTRUCTION
from command_center.coding.integration_config import IntegrationConfig, Tariff
from command_center.coding.spec import BASE_SHA, FIRST, CORRECT


def config(**changes):
    # Numbers are fake fixture accounting, NEVER a real tariff.
    fields = {'mode': 'http_mock', 'synthetic_repository': 'fixture/acc-f2-synthetic-test',
              'daily_nano_rub': 10_000_000, 'monthly_nano_rub': 100_000_000,
              'tariff': Tariff(model='fixture-model', input_nano_rub=10, output_nano_rub=20,
                               context_tokens=8192, max_output_tokens=128,
                               confirmed=True, evidence='HTTP fixture, not a real tariff')}
    return IntegrationConfig(**{**fields, **changes})


class Credentials:
    values = {'openai': 'synthetic-openai-fixture-value-only',
              'github-installation-token': 'synthetic-github-fixture-value-only'}
    def get(self, ref):
        if ref not in self.values:
            raise PermissionError('credential_not_connected')
        return self.values[ref]


class FakeHTTP:
    def __init__(self, scenario='normal', model='fixture-model'):
        self.calls, self.ai_calls, self.prs, self.branches, self.objects = [], 0, [], {}, {}
        self.scenario, self.before, self.after = scenario, None, None
        self.fail_status, self.fail_path = None, ''
        self.base_sha = BASE_SHA
        self.model = model
        self.repository_id = 725000001  # Public fixture ID only, not an actual repository.
        self.protected = True

    def handle(self, request):
        self.calls.append((request.method, request.url.path))
        if self.before:
            self.before(request)
        if self.fail_status and request.url.path.endswith(self.fail_path):
            return httpx.Response(self.fail_status, json={'message': 'fixture failure'})
        data = self.dispatch(request)
        if self.after:
            self.after(request)
        if isinstance(data, httpx.Response):
            return data
        return httpx.Response(200 if request.method == 'GET' or request.url.host == 'api.openai.com' else 201,
                              json=data, headers={'x-request-id': 'fixture-request-id'})

    def dispatch(self, request):
        body = json.loads(request.content) if request.content else None
        if request.url.host == 'api.openai.com':
            assert request.url.path == '/v1/responses' and request.method == 'POST'
            assert set(body) == {'model', 'store', 'service_tier', 'max_output_tokens', 'input', 'text'}
            assert body['service_tier'] == 'default'
            assert body['store'] is False and body['model'] == self.model
            assert body['text']['format'] == FORMAT and body['input'][0] == {'role': 'developer', 'content': INSTRUCTION}
            context = json.loads(body['input'][1]['content'])
            assert not any(v in json.dumps(context) for v in Credentials.values.values())
            self.ai_calls += 1
            if self.ai_calls == 2:
                assert context['checks']['passed'] is False and context['source'] == FIRST
            source = FIRST if self.ai_calls == 1 else CORRECT
            output = [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                       'content': [{'type': 'output_text', 'text': json.dumps({'source': source}), 'annotations': []}]}]
            if self.scenario == 'tool_injection':
                output = [{'type': 'function_call', 'name': 'get_secret', 'arguments': '{}'}]
            if self.scenario == 'scope_injection':
                output[0]['content'][0]['text'] = json.dumps({'source': CORRECT, 'repository': 'CRM'})
            if self.scenario == 'credential_echo':
                output[0]['content'][0]['text'] = json.dumps({'source': '# ' + Credentials.values['openai'] + '\n' + CORRECT})
            return {'id': 'resp_fixture_' + str(self.ai_calls), 'object': 'response', 'model': self.model,
                    'service_tier': 'default',
                    'created_at': 1, 'status': 'completed', 'output': output,
                    'usage': {'input_tokens': 100, 'output_tokens': 32, 'total_tokens': 132}}
        assert request.url.host == 'api.github.com'
        prefix = '/repos/fixture/acc-f2-synthetic-test'
        assert request.url.path.startswith(prefix)
        path = request.url.path[len(prefix):]
        if request.method == 'GET':
            if path == '':
                return {'id': self.repository_id, 'full_name': 'fixture/acc-f2-synthetic-test',
                        'archived': False, 'disabled': False, 'permissions': {'admin': False, 'push': True}}
            if path == '/branches/main':
                return {'name': 'main', 'protected': self.protected, 'commit': {'sha': self.base_sha}}
            if path == '/git/ref/heads/main':
                return {'ref': 'refs/heads/main', 'object': {'sha': self.base_sha}}
            if path.startswith('/git/ref/heads/'):
                branch = path.removeprefix('/git/ref/heads/')
                return {'ref': 'refs/heads/' + branch, 'object': {'sha': self.branches.get(branch)}}
            if path == '/pulls':
                return self.prs
            sha = path.rsplit('/', 1)[-1]
            return {'sha': sha} if sha in self.objects else httpx.Response(404, json={'message': 'not found'})
        if path == '/git/blobs':
            assert body['encoding'] == 'utf-8'
            obj = Blob.from_string(body['content'].encode())
        elif path == '/git/trees':
            obj = Tree()
            for item in body['tree']:
                assert item['mode'] == '100644' and item['type'] == 'blob'
                obj.add(item['path'].encode(), 0o100644, item['sha'].encode())
        elif path == '/git/commits':
            obj = Commit()
            obj.tree = body['tree'].encode()
            obj.parents = [p.encode() for p in body['parents']]
            obj.message = body['message'].encode()
            for field in ('author', 'committer'):
                identity = body[field]
                setattr(obj, field, (identity['name'] + ' <' + identity['email'] + '>').encode())
                clock = 'author' if field == 'author' else 'commit'
                setattr(obj, clock + '_time', int(datetime.fromisoformat(identity['date']).timestamp()))
                setattr(obj, clock + '_timezone', 0)
        elif path == '/git/refs':
            assert body['ref'].startswith('refs/heads/f2/task-')
            branch = body['ref'].removeprefix('refs/heads/')
            assert branch not in self.branches
            self.branches[branch] = body['sha']
            return {'ref': body['ref'], 'object': {'sha': body['sha']}}
        elif path == '/pulls':
            assert body['draft'] is True and body['base'] == 'main'
            result = {'id': 101, 'number': 1, 'draft': True, 'state': 'open', 'body': body['body'],
                      'html_url': 'https://github.com/fixture/acc-f2-synthetic-test/pull/1',
                      'base': {'sha': self.base_sha, 'ref': 'main', 'repo': {'full_name': 'fixture/acc-f2-synthetic-test'}},
                      'head': {'sha': self.branches[body['head']], 'ref': body['head'],
                               'repo': {'full_name': 'fixture/acc-f2-synthetic-test'}}}
            self.prs.append(result)
            return result
        else:
            raise AssertionError('unsupported fixture endpoint')
        self.objects[obj.id.decode()] = obj
        return {'sha': obj.id.decode()}
