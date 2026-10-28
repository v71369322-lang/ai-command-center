"""Isolated cloud container proof with fake Bot API; never a host deployment."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

from command_center.local_docker import run as docker
from command_center.telegram_transport import TelegramConnection
from command_center.store import digest


CHILD = r'''
import json
import httpx
from command_center.store import Store
from command_center.telegram_service import TelegramService, service_settings
from command_center.telegram_transport import ConfiguredTelegramHTTP, connection
config=connection('/run/telegram/connection.json')
owner=config.owner_id
calls=[]
sent=[]
def handle(request):
    method=request.url.path.rsplit('/',1)[-1]
    body=json.loads(request.content)
    calls.append(method)
    if method=='getMe':
        result={'id':config.bot_id,'is_bot':True,'first_name':'Public fixture bot'}
    elif method=='getWebhookInfo':
        result={'url':'','has_custom_certificate':False,'pending_update_count':0}
    elif method=='getUpdates':
        values=['Synthetic container service request','/tasks','/status 00000000-0000-0000-0000-000000000001',
                '/requests','/request 1']
        result=[{'update_id':i,'message':{
            'message_id':100+i,'date':1700000000,'from':{'id':owner,'is_bot':False,'first_name':'Public fixture owner'},
            'chat':{'id':owner,'type':'private'},'text':value}}
            for i,value in enumerate(values,1) if i>=body['offset']]
    elif method=='sendMessage':
        assert body['chat_id']==owner
        sent.append(body['text'])
        result={'message_id':len(sent),'date':1700000000,'chat':{'id':owner,'type':'private'}}
    else: raise AssertionError('unexpected method')
    return httpx.Response(200,json={'ok':True,'result':result})
store=Store(service_settings())
from command_center.store import digest
client=ConfiguredTelegramHTTP('/run/telegram/connection.json',digest(config.model_dump()),
    store.settings.source_revision,transport=httpx.MockTransport(handle))
try:
    result=TelegramService(store,client,poll_seconds=0).run(max_cycles=2)
    assert result['completed_cycles']==2 and result['live_verified'] is False
    assert calls.count('sendMessage')==5
    assert any('пока нет' in value for value in sent)
    assert any('не найдена' in value for value in sent)
    assert any('Запрос №1 сохранён' in value for value in sent)
    assert sum('Текст запроса (не команда):' in value and 'Synthetic container service request' in value
               for value in sent)==2
    assert all(len(value)<=4096 for value in sent)
    print(json.dumps({'mode':'http_mock','cycles':2,'read_only_queries':4,'actual_telegram_contacted':False}))
finally:
    client.close();store.engine.dispose()
'''


def command(*args):
    result = docker(*args, timeout=90)
    if result.returncode:
        raise RuntimeError('telegram_container_smoke_failed:' + args[0])
    return result.stdout


def main():
    revision = os.environ['F1_SOURCE_REVISION']
    if (subprocess.check_output(['git', 'status', '--porcelain']).strip()
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() != revision):
        raise ValueError('telegram_smoke_clean_pinned_source_required')
    image = json.loads(command('image', 'inspect', 'acc-f1-app:local'))[0]
    if image['Config']['Labels']['org.opencontainers.image.revision'] != revision:
        raise ValueError('telegram_smoke_image_revision_mismatch')
    root = Path('.runtime/telegram-container-' + uuid4().hex).resolve()
    root.mkdir(mode=0o700)
    name = 'acc-tg-service-smoke-' + uuid4().hex
    try:
        owner_id = 1000000000 + int(uuid4().hex[:10], 16)
        bot_id = 1000000000 + int(uuid4().hex[:10], 16)
        config = TelegramConnection(mode='http_mock', owner_id=owner_id, bot_id=bot_id,  # nosec B106: public file reference, not a token value
                                    source_revision=revision, token_file='/run/telegram/token')
        for filename, value in [('token', str(bot_id) + ':' + 'PUBLIC_SYNTHETIC_NOT_AN_ACTUAL_KEY_12345'),
                                ('connection.json', config.model_dump_json())]:
            fd = os.open(root / filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as file:
                file.write(value)
        args = ['run', '--name', name, '--network=acc-f1_control', '--read-only', '--cap-drop=ALL',
                '--security-opt=no-new-privileges', f'--user={os.getuid()}:{os.getgid()}',
                '--memory=128m', '--cpus=.25', '--pids-limit=32', '--tmpfs=/tmp:size=16m',
                '--log-driver=local', '--log-opt=max-size=1m', '--log-opt=max-file=2',
                '--mount', f'type=bind,src={root},dst=/run/telegram,readonly']
        env = {'F1_SOURCE_REVISION': revision, 'F1_DB_USER': 'f1_app', 'F1_DB_HOST': 'db',
               'F1_DB_PASSWORD_FILE': '/run/synthetic/db_password'}
        for key, value in env.items():
            args += ['--env', key + '=' + value]
        for filename in ('db_password',):
            args += ['--mount', f'type=bind,src={Path(".runtime/secrets", filename).resolve()},dst=/run/synthetic/{filename},readonly']
        result = json.loads(command(*args, image['Id'], 'python', '-c', CHILD))
        info = json.loads(command('inspect', name))[0]
        targets = {'/run/telegram', '/run/synthetic/db_password'}
        if (result.get('mode') != 'http_mock' or result.get('actual_telegram_contacted') is not False
                or info['HostConfig']['Privileged'] or info['HostConfig']['CapDrop'] != ['ALL']
                or not info['HostConfig']['ReadonlyRootfs'] or info['HostConfig']['PortBindings']
                or info['HostConfig']['Memory'] != 128*1024*1024 or info['HostConfig']['PidsLimit'] != 32
                or info['HostConfig']['NanoCpus'] != 250000000 or info['HostConfig']['NetworkMode'] != 'acc-f1_control'
                or info['Config']['User'] != f'{os.getuid()}:{os.getgid()}'
                or not any(s.split(':')[0] == 'no-new-privileges' for s in info['HostConfig']['SecurityOpt'])
                or {m['Destination'] for m in info['Mounts']} != targets
                or any(m['RW'] or 'docker.sock' in m['Source'] for m in info['Mounts'])):
            raise ValueError('telegram_smoke_isolation_invalid')
        report = {'revision': revision, 'status': 'PASS', **result,
                  'runtime_mode': 'CLOUD_ROOTFUL_TEST_ONLY', 'rootless_host_verified': False,
                  'connection_digest': digest(config.model_dump()), 'vps_contacted': False}
        Path('.runtime/telegram-container.json').write_text(json.dumps(report, indent=2) + '\n')
        print('Telegram service container → actual PG → mock HTTP → durable numbered requests/status replies; no socket/ports: PASS')
    finally:
        removed = docker('rm', '--force', name, timeout=15)
        absent = docker('inspect', name, timeout=5)
        healthy = docker('info', '--format={{.ServerVersion}}', timeout=5)
        if removed.returncode or absent.returncode == 0 or healthy.returncode:
            raise RuntimeError('telegram_smoke_cleanup_unconfirmed')
        shutil.rmtree(root)


if __name__ == '__main__':
    main()
