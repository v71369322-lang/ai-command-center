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
from command_center.telegram_menu import BUTTONS, keyboard
from command_center.telegram_project_picker import keyboard as picker_keyboard
config=connection('/run/telegram/connection.json')
owner=config.owner_id
calls=[]
sent=[]
menus=[]
pickers=[]
resume_cards=[]
resume_mode=False
def require(condition, code):
    if not condition:
        raise RuntimeError('telegram_smoke_assertion:' + code)
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
                '/requests','/request 1','/projects','/assign 1 lnauto 0','/request 1',
                '/projects','/requests lnauto','/requests vanilla-sugar','/requests unassigned','/requests all',
                '/coding_plan','/coding_demo','/menu',*[label for label,_ in BUTTONS],'/readiness']
        result=[{'update_id':i,'message':{
            'message_id':100+i,'date':1700000000,'from':{'id':owner,'is_bot':False,'first_name':'Public fixture owner'},
            'chat':{'id':owner,'type':'private'},'text':value}}
            for i,value in enumerate(values,1) if i>=body['offset']]
        if body['offset']==0:
            result=result[:1]  # The picker must be observed SENT before its callback.
        else:
            for index,value in enumerate(result):
                if value['update_id']==7:
                    result[index]={'update_id':7,'callback_query':{'id':'public-project-choice',
                        'from':{'id':owner,'is_bot':False},'data':'pj:1:0:lnauto',
                        'message':{'message_id':1,'chat':{'id':owner,'type':'private'}}}}
            result=result[:20]  # Match the bridge and Bot API batch ceiling.
        if resume_mode:
            result=[]
            if body['offset']<=100:
                result=[{'update_id':100,'message':{'message_id':200,'date':1700000000,
                    'from':{'id':owner,'is_bot':False},'chat':{'id':owner,'type':'private'},'text':'/resume'}}]
            elif body['offset']==101:
                message_id,data=resume_cards[-1]
                result=[{'update_id':101,'callback_query':{'id':'public-normal-resume',
                    'from':{'id':owner,'is_bot':False},'data':data,
                    'message':{'message_id':message_id,'chat':{'id':owner,'type':'private'}}}}]
    elif method=='answerCallbackQuery':
        require(body in ({'callback_query_id':'public-project-choice'},{'callback_query_id':'public-normal-resume'}), 'callback_body')
        result=True
    elif method=='sendMessage':
        require(body['chat_id']==owner, 'send_chat')
        sent.append(body['text'])
        if 'keyboard' in body.get('reply_markup',{}):
            menus.append(body['reply_markup'])
        elif 'inline_keyboard' in body.get('reply_markup',{}):
            data=body['reply_markup']['inline_keyboard'][0][0]['callback_data']
            if data.startswith('rs:'):
                resume_cards.append((len(sent),data))
            else:
                pickers.append(body['reply_markup'])
        result={'message_id':len(sent),'date':1700000000,'chat':{'id':owner,'type':'private'}}
    else: raise AssertionError('unexpected method')
    return httpx.Response(200,json={'ok':True,'result':result})
store=Store(service_settings())
from command_center.store import digest
client=ConfiguredTelegramHTTP('/run/telegram/connection.json',digest(config.model_dump()),
    store.settings.source_revision,transport=httpx.MockTransport(handle))
try:
    service=TelegramService(store,client,poll_seconds=0)
    # Six menu commands add durable replies ahead of the asynchronous coding
    # result. Keep bounded scheduling slack so a healthy worker result reaches
    # the transport before exact delivery assertions run.
    result=service.run(max_cycles=48)
    require(result['completed_cycles']==48 and result['live_verified'] is False, 'initial_cycles')
    # Fixed message updates, every menu button, and the coding-result
    # notification. The project-choice callback is acknowledged separately and
    # therefore is not a sendMessage call. Keep this coupled to the canonical
    # menu instead of silently pinning the smoke to an obsolete button count.
    require(calls.count('sendMessage')==16+len(BUTTONS), 'send_count')
    require(sum('Состояние AI Commander' in value and 'Состояние gateway неизвестно' in value
                and 'Сводка не запускает задачи' in value for value in sent)==1, 'readiness')
    require(menus==[keyboard(),keyboard()], 'menus')
    require(pickers==[picker_keyboard('1',0),picker_keyboard('1',0),picker_keyboard('1',1)], 'pickers')
    require(calls.count('answerCallbackQuery')==1, 'callback_count')
    require(any('пока нет' in value for value in sent), 'empty_tasks')
    require(any('не найдена' in value for value in sent), 'missing_task')
    require(any('Запрос №1 сохранён' in value for value in sent), 'request_saved')
    require(sum('Текст запроса (не команда):' in value and 'Synthetic container service request' in value
                for value in sent)==6, 'request_body_count')
    require(any('Проект: LNAuto. Версия назначения: 1' in value for value in sent), 'assignment')
    require(any('LNAuto: 1\n/requests lnauto' in value for value in sent), 'project_counts')
    require(any('Очередь: LNAuto. Ожидают планирования: 1.' in value for value in sent), 'lnauto_queue')
    require(any('Очередь: Ваниль и Сахар. Ожидают планирования: 0.' in value for value in sent), 'vanilla_queue')
    require(any('Очередь: Не распределены. Ожидают планирования: 0.' in value for value in sent), 'unassigned_queue')
    require(any('Тестовый разработчик (mock) принят:' in value for value in sent), 'coding_accepted')
    require(any('Проверка 1: найдена ошибка. Проверка 2: пройдена после исправления.' in value
                and 'Результат независимо проверен' in value
                and 'PR подготовлен в mock-режиме, не опубликован' in value for value in sent), 'coding_result')
    from command_center.models import TelegramInbox
    row_id=service.bridge.profile+':15'
    with store.transaction() as session:
        task_id=session.get(TelegramInbox,row_id).task_id
    coding_task=store.get(task_id)
    require(coding_task['state']=='SUCCEEDED', 'coding_state')
    require([r['checks']['passed'] for r in coding_task['coding']['test_runs']]==[False,True], 'coding_checks')
    require(coding_task['coding']['pr']['published'] is False and coding_task['coding']['pr']['url'] is None, 'coding_pr')
    # Run the real service/PG action from a separately confirmed normal stop.
    # The callback is returned only after its sendMessage receipt was observed.
    store.halt('owner')
    before=store.snapshot()
    resume_mode=True
    resumed=service.run(max_cycles=3)
    after=store.snapshot()
    require(resumed['completed_cycles']==3 and len(resume_cards)==1, 'resume_cycles')
    require(after['halted'] is False and after['epoch']==before['epoch']+1, 'resume_state')
    require(after['budget']==before['budget'] and after['tasks']==before['tasks'], 'resume_scope')
    require(any('Обычная остановка снята для новых разрешённых задач' in value for value in sent), 'resume_reply')
    require(all(len(value)<=4096 for value in sent), 'message_length')
    print(json.dumps({'mode':'http_mock','cycles':48,'read_only_queries':14+len(BUTTONS),'project_assignments':1,
        'readiness_summary_delivered':True,'readiness_ai_status':'unknown_without_gateway_profile',
        'owner_menu_replies':len(menus),'menu_buttons':len(BUTTONS),
        'project_picker_cards':len(pickers),'project_choice_callbacks':1,
        'coding_task_id':task_id,'coding_repair_checks':[False,True],'mock_pr_published':False,
        'normal_stop_resume_confirmed':True,'resume_confirmation_cards':len(resume_cards),
        'actual_telegram_contacted':False}))
finally:
    client.close();store.engine.dispose()
'''


def command(*args):
    result = docker(*args, timeout=90)
    if result.returncode:
        if result.stderr:
            print(result.stderr.decode(errors='replace')[-2000:])
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
        print('Telegram service container → fake Bot API → actual PG/Redis/worker/broker → coding repair/replay → mock PR → Telegram report; no socket/ports: PASS')
    finally:
        removed = docker('rm', '--force', name, timeout=15)
        absent = docker('inspect', name, timeout=5)
        healthy = docker('info', '--format={{.ServerVersion}}', timeout=5)
        if removed.returncode or absent.returncode == 0 or healthy.returncode:
            raise RuntimeError('telegram_smoke_cleanup_unconfirmed')
        shutil.rmtree(root)


if __name__ == '__main__':
    main()
