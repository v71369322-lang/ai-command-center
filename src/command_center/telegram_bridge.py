"""Telegram intents reuse F1 authority; external transport is separately scoped."""
from datetime import timedelta
import hashlib
import json
import re
import secrets
from uuid import UUID, uuid5, NAMESPACE_URL

import httpx
from sqlalchemy import select, func, and_, or_

from .api import Command
from .models import TelegramInbox, TelegramDelivery, TelegramCard, Control, Audit, Task
from .store import Denied, canonical, digest
from .telegram_requests import capture_receipt, request_reply
from .telegram_menu import BUTTONS, keyboard
from .telegram_transport import ConfiguredTelegramHTTP, token_fingerprint
from .telegram_experiment_scope import RecoveryBridge, key as experiment_key


class MockTelegramHTTP:
    """Documented Bot API method shapes through MockTransport ONLY."""
    def __init__(self, transport):
        if not isinstance(transport, httpx.MockTransport):
            raise ValueError('telegram_live_transport_disabled')
        self.client = httpx.Client(transport=transport, timeout=5, trust_env=False,
                                  base_url='https://api.telegram.org/bot123456789:PUBLIC_SYNTHETIC_FIXTURE/')

    def call(self, method, body):
        if method not in {'getUpdates', 'sendMessage'}:
            raise ValueError('telegram_method_forbidden')
        response = self.client.post(method, json=body)
        if len(response.content) > 65536:
            raise ValueError('telegram_response_too_large')
        response.raise_for_status()
        value = response.json()
        if value.get('ok') is not True or 'result' not in value:
            raise ValueError('telegram_response_invalid')
        return value['result']

    def close(self):
        self.client.close()


class TelegramBridge:
    def __init__(self, store, client, owner_id):
        if (type(owner_id) is not int or not 0 < owner_id < 2**52
                or not isinstance(client, (MockTelegramHTTP, ConfiguredTelegramHTTP))):
            raise ValueError('synthetic_private_owner_binding_required')
        self.store, self.client, self.owner = store, client, owner_id
        self.profile = digest({'owner': owner_id, 'revision': store.settings.source_revision, 'mode': 'http_mock'})
        if isinstance(client, ConfiguredTelegramHTTP):
            if client.owner != owner_id or client.revision != store.settings.source_revision:
                raise Denied('telegram_connection_scope_mismatch')
            # Stable across code/credential rotation: remote Update IDs must not
            # be treated as new work when the application is upgraded.
            self.profile = digest({'owner': owner_id, 'bot_id': client.bot_id, 'mode': client.mode})

    def guard(self):
        if isinstance(self.client, ConfiguredTelegramHTTP):
            self.client.check_enabled()
            if getattr(self.client, 'runtime_guard', None):
                self.client.runtime_guard()

    def enqueue(self, session, key, text, markup=None):
        oid = digest({'profile': self.profile, 'event': key})
        if not session.get(TelegramDelivery, oid):
            if session.scalar(select(func.count()).select_from(TelegramDelivery)) >= 1000:
                raise Denied('telegram_delivery_capacity')
            body = {'chat_id': self.owner, 'text': text}
            if markup:
                body['reply_markup'] = markup
            session.add(TelegramDelivery(id=oid, profile=self.profile, body=body, state='NEW'))
            session.flush()
            self.store.audit(session, 'telegram_delivery_queued', 'system', delivery_id=oid, request_hash=digest(body))
        return oid

    @staticmethod
    def card_binding(card):
        return digest({k: getattr(card, k) for k in ('profile', 'delivery_id', 'task_id', 'version',
            'payload_hash', 'epoch', 'revision')} | {'expires_at': card.expires_at.isoformat()})

    def normalize(self, update):
        if not isinstance(update, dict) or len(json.dumps(update).encode()) > 8192:
            raise Denied('telegram_update_size_or_type')
        uid = update.get('update_id')
        if type(uid) is not int or not 0 <= uid < 2**53:
            raise Denied('telegram_update_id_invalid')
        callback = update.get('callback_query')
        if callback is not None and not isinstance(callback, dict):
            raise Denied('telegram_callback_invalid')
        message = callback.get('message') if isinstance(callback, dict) else update.get('message')
        sender = callback.get('from') if isinstance(callback, dict) else (
            message.get('from') if isinstance(message, dict) else None)
        chat = message.get('chat') if isinstance(message, dict) else None
        if (not isinstance(message, dict) or not isinstance(sender, dict) or not isinstance(chat, dict)
                or type(sender.get('id')) is not int or sender['id'] != self.owner
                or sender.get('is_bot') is not False
                or type(chat.get('id')) is not int or chat['id'] != self.owner or chat.get('type') != 'private'
                or 'forward_origin' in message or 'sender_chat' in message):
            raise Denied('telegram_owner_private_chat_required')
        if callback is not None:
            token = callback.get('data', '')
            if (not isinstance(token, str) or type(message.get('message_id')) is not int
                    or message['message_id'] <= 0):
                raise Denied('telegram_callback_invalid')
            if token.startswith('pj:'):
                from .telegram_project_picker import parse_callback
                intent = parse_callback(token) | {'message_id': message['message_id']}
            elif token.startswith('rs:'):
                from .telegram_control import parse_callback
                intent = parse_callback(token) | {'message_id': message['message_id']}
            elif token.startswith(('fx:', 'rx:')):
                from .telegram_experiment_authorize import parse_callback
                intent = parse_callback(token) | {'message_id': message['message_id']}
            elif token.startswith('cl:'):
                from .telegram_calendar import parse_callback
                intent = parse_callback(token) | {'message_id': message['message_id']}
            elif token.startswith('vr:'):
                from .telegram_voice_transcripts import parse_callback
                intent = parse_callback(token) | {'message_id': message['message_id']}
            else:
                if not re.fullmatch(r'tg:[A-Za-z0-9_-]{32}', token):
                    raise Denied('telegram_callback_invalid')
                intent = {'kind': 'approve', 'card': hashlib.sha256(token[3:].encode()).hexdigest(),
                          'message_id': message['message_id']}
            if isinstance(self.client, ConfiguredTelegramHTTP):
                query_id = callback.get('id')
                if (not isinstance(query_id, str) or not 1 <= len(query_id) <= 128
                        or self.client.sensitive(query_id)):
                    raise Denied('telegram_callback_invalid')
                intent['callback_query_id'] = query_id
            return str(uid), intent
        value = message.get('text')
        if value is None and 'voice' in message:
            sensitive = self.client.sensitive if isinstance(self.client, ConfiguredTelegramHTTP) else lambda _: False
            if message.get('caption') == '/calendar':
                from .telegram_calendar_voice import parse_message
            else:
                from .telegram_voice_requests import parse_message
            return str(uid), parse_message(message, sensitive)
        self.check_text(value)
        value = dict(BUTTONS).get(value, value)
        if value.startswith('/demo '):
            try:
                payload = Command(kind='approved_render', values={'request': value[6:]}).model_dump()
            except ValueError:
                raise Denied('telegram_demo_scope_invalid') from None
            return str(uid), {'kind': 'demo', 'payload': payload}
        if value.startswith('/cancel '):
            try:
                task_id = str(UUID(value[8:]))
            except ValueError:
                raise Denied('telegram_task_id_invalid') from None
            return str(uid), {'kind': 'cancel', 'task_id': task_id}
        if value == '/stop':
            return str(uid), {'kind': 'stop'}
        if value == '/resume':
            return str(uid), {'kind': 'resume_request'}
        if value.split()[:1] == ['/resume']:
            raise Denied('telegram_resume_arguments_forbidden')
        if value == '/tasks':
            return str(uid), {'kind': 'tasks'}
        if value == '/readiness':
            return str(uid), {'kind': 'readiness'}
        recovery_commands = {'/recovery': 'recovery', '/prepare_recovery': 'prepare_recovery',
                             '/authorize_recovery': 'recovery_authorize_request',
                             '/cancel_recovery': 'cancel_recovery', '/watch_recovery': 'watch_recovery',
                             '/unwatch_recovery': 'unwatch_recovery'}
        if value in recovery_commands:
            return str(uid), {'kind': recovery_commands[value]}
        if value.split()[:1] and value.split()[0] in recovery_commands:
            raise Denied('telegram_recovery_arguments_forbidden')
        if value == '/experiment':
            return str(uid), {'kind': 'experiment'}
        if value == '/prepare_experiment':
            return str(uid), {'kind': 'prepare_experiment'}
        if value == '/authorize_experiment':
            return str(uid), {'kind': 'experiment_authorize_request'}
        if value.split()[:1] == ['/authorize_experiment']:
            raise Denied('telegram_experiment_authorize_arguments_forbidden')
        if value.split()[:1] == ['/prepare_experiment']:
            raise Denied('telegram_experiment_prepare_arguments_forbidden')
        if value == '/cancel_experiment':
            return str(uid), {'kind': 'cancel_experiment'}
        if value.split()[:1] == ['/cancel_experiment']:
            raise Denied('telegram_experiment_cancel_arguments_forbidden')
        if value in {'/watch_experiment', '/unwatch_experiment'}:
            return str(uid), {'kind': value[1:]}
        if value.split()[:1] in [['/watch_experiment'], ['/unwatch_experiment']]:
            raise Denied('telegram_experiment_watch_arguments_forbidden')
        if value.split()[:1] == ['/experiment']:
            raise Denied('telegram_experiment_arguments_forbidden')
        if value.split()[:1] == ['/readiness']:
            raise Denied('telegram_readiness_arguments_forbidden')
        if value in {'/coding_demo', '/coding_plan'}:
            return str(uid), {'kind': value[1:]}
        if value.split()[:1] in [['/coding_demo'], ['/coding_plan']]:
            raise Denied('telegram_coding_fixed_scope_required')
        if value == '/requests':
            return str(uid), {'kind': 'requests'}
        if value.split()[:1] == ['/requests']:
            from .project_inbox import IDS
            parts = value.split()
            if len(parts) != 2 or parts[1] not in IDS | {'all', 'unassigned'}:
                raise Denied('telegram_project_filter_invalid')
            return str(uid), {'kind': 'requests', 'project': parts[1]}
        if value == '/projects':
            return str(uid), {'kind': 'projects'}
        if value.split()[:1] == ['/project']:
            from .project_catalog import IDS
            parts = value.split()
            if len(parts) != 2 or parts[1] not in IDS:
                raise Denied('telegram_project_reference_invalid')
            return str(uid), {'kind': 'project', 'project_id': parts[1]}
        if value in {'/voice', '/system'}:
            return str(uid), {'kind': value[1:]}
        if value.split()[:1] in [['/voice'], ['/system']]:
            raise Denied('telegram_query_arguments_forbidden')
        if value == '/calendar' or value.split()[:1] == ['/calendar']:
            from .telegram_calendar import parse_command
            return str(uid), parse_command(value)
        attention_commands = {'/attention': 'attention', '/reminders': 'reminders'}
        if value in attention_commands:
            return str(uid), {'kind': attention_commands[value]}
        if value.split()[:1] and value.split()[0] in attention_commands:
            raise Denied('telegram_attention_arguments_forbidden')
        if value == '/plan':
            return str(uid), {'kind': 'help'}
        if value.split()[:1] == ['/plan']:
            from .telegram_plan_review import MAX_PAGES
            from .request_plan_store import MAX_PROPOSALS
            parts = value.split()
            version, page = (parts[2], parts[3]) if len(parts) == 4 else ('1', '1')
            if (len(parts) not in {2, 4} or not re.fullmatch(r'0|[1-9][0-9]{0,15}', parts[1])
                    or int(parts[1]) >= 2**53 or not re.fullmatch(r'[1-9][0-9]?', page)
                    or int(page) > MAX_PAGES or not re.fullmatch(r'[1-9][0-9]{0,2}', version)
                    or int(version) > MAX_PROPOSALS):
                raise Denied('telegram_plan_reference_invalid')
            return str(uid), {'kind': 'plan_review', 'number': parts[1], 'page': int(page),
                             'version': int(version) if len(parts) == 4 else None}
        if value.startswith('/assign '):
            from .project_inbox import IDS
            parts = value.split()
            if (len(parts) != 4 or not re.fullmatch(r'0|[1-9][0-9]{0,15}', parts[1])
                    or int(parts[1]) >= 2**53 or parts[2] not in IDS | {'none'}
                    or not re.fullmatch(r'0|[1-9][0-9]{0,3}', parts[3]) or int(parts[3]) > 1000):
                raise Denied('telegram_project_assignment_invalid')
            return str(uid), {'kind': 'assign', 'number': parts[1],
                             'project_id': None if parts[2] == 'none' else parts[2], 'version': int(parts[3])}
        if value.startswith('/request '):
            number = value[9:]
            if not re.fullmatch(r'0|[1-9][0-9]{0,15}', number) or int(number) >= 2**53:
                raise Denied('telegram_request_number_invalid')
            return str(uid), {'kind': 'request', 'number': number}
        if value.startswith('/status '):
            try:
                task_id = str(UUID(value[8:]))
            except ValueError:
                raise Denied('telegram_task_id_invalid') from None
            return str(uid), {'kind': 'status', 'task_id': task_id}
        if value in {'/start', '/help', '/menu', '/status', '/request', '/assign'}:
            return str(uid), {'kind': 'help'}
        captured = value.removeprefix('/task ')
        if not captured.strip():
            raise Denied('telegram_empty_request')
        return str(uid), {'kind': 'capture', 'text': captured}

    def check_text(self, value):
        """Same limits and secret guard for incoming text and stored previews."""
        if not isinstance(value, str) or not 1 <= len(value.encode()) <= 2000:
            raise Denied('telegram_text_only')
        known = [*self.store.settings.identities.values(), self.store.settings.redis_password,
                 self.store.settings.database_url.password]
        if (any(v and v in value for v in known)
                or (isinstance(self.client, ConfiguredTelegramHTTP) and self.client.sensitive(value))
                or re.search(r'PRIVATE KEY|\bsk-[A-Za-z0-9_-]{20,}|\bgh[pousr]_[A-Za-z0-9]{20,}|\b[0-9]{6,20}:[A-Za-z0-9_-]{30,128}', value)):
            raise Denied('telegram_secret_content_forbidden')

    def finish(self, session, iid, text, markup=None):
        self.guard()
        self.store.check_audit(session)
        row = session.get(TelegramInbox, iid)
        if row.state == 'DONE':
            raise Denied('telegram_update_already_committed')
        row.state = 'DONE'
        return self.enqueue(session, iid + ':reply', text, markup)

    def receive(self, update):
        self.guard()
        update_id, intent = self.normalize(update)
        iid = self.profile + ':' + update_id
        with self.store.transaction() as session:
            self.store.check_audit(session)
            row = session.get(TelegramInbox, iid)
            if row:
                if row.fingerprint != digest(intent):
                    raise Denied('telegram_update_reused_with_different_content')
                if row.state in {'DONE', 'NEEDS_PLANNING'}:
                    return {'inbox_id': iid, 'state': row.state, 'task_id': row.task_id}
            else:
                admission = {}
                if intent['kind'] == 'coding_demo':
                    control = session.get(Control, 1)
                    if control.halted or control.recovery:
                        raise Denied('control_blocked')
                    admission = {'admission_epoch': control.epoch,
                                 'expires_at': (self.store.now(session) + timedelta(seconds=120)).isoformat()}
                scope = RecoveryBridge(self) if 'recovery' in intent['kind'] else self
                if intent['kind'] in {'cancel_experiment', 'cancel_recovery'}:
                    from .telegram_experiment_cancel import bind
                    admission[experiment_key(scope, 'experiment_cancel_binding')] = bind(scope, session)
                if intent['kind'] in {'prepare_experiment', 'prepare_recovery'}:
                    from .telegram_experiment_prepare import bind
                    admission = {'admission_epoch': session.get(Control, 1).epoch,
                                 experiment_key(scope, 'experiment_prepare_binding'): bind(scope, session)}
                if session.scalar(select(func.count()).select_from(TelegramInbox)) >= 1000:
                    raise Denied('telegram_inbox_capacity')
                session.add(TelegramInbox(id=iid, profile=self.profile, fingerprint=digest(intent), intent=intent,
                                         state='RECEIVED', created_at=self.store.now(session)))
                self.store.audit(session, 'telegram_update_received', 'owner', update_id=update_id, profile=self.profile,
                                 intent_hash=digest(intent), **admission)
        return self._apply_pending(iid, intent)

    def _apply_pending(self, iid, intent):
        self.guard()
        kind = intent['kind']
        scope = RecoveryBridge(self) if 'recovery' in kind else self
        if kind in {'experiment_authorize_request', 'recovery_authorize_request'}:
            from .telegram_experiment_authorize import issue
            with self.store.transaction() as session:
                self.guard()
                self.store.check_audit(session)
                if session.get(TelegramInbox, iid).state != 'DONE':
                    issue(scope, session, iid)
        elif kind in {'experiment_authorize_confirm', 'recovery_authorize_confirm'}:
            from .telegram_experiment_authorize import confirm
            confirm(scope, iid, intent)
        elif kind in {'prepare_experiment', 'prepare_recovery'}:
            from .telegram_experiment_prepare import apply
            apply(scope, iid)
        elif kind == 'coding_demo':
            from .telegram_coding import accepted, exercise
            self.store.create('owner', 'tg:' + iid, exercise(),
                              _scope_installer=lambda session, task: accepted(self, session, iid, task))
        elif kind == 'demo':
            # Crash-safe stable F1 idempotency key. A duplicate never creates another task.
            task = self.store.create('owner', 'tg:' + iid, intent['payload'])
            with self.store.transaction() as session:
                self.store.check_audit(session)
                row = session.get(TelegramInbox, iid)
                if row.state != 'DONE':
                    row.task_id = task['id']
                    current = self.store.task(session, task['id'])
                    if current.state != 'WAITING_APPROVAL':
                        raise Denied('telegram_demo_not_waiting')
                    token = secrets.token_urlsafe(24)
                    expires = self.store.now(session) + timedelta(seconds=120)
                    markup = {'inline_keyboard': [[{'text': 'Подтвердить синтетический тест', 'callback_data': 'tg:' + token}]]}
                    text = (f'Только синтетический тест. Task {current.id}; версия {current.version}; '
                            f'Параметры: {current.payload["values"]}; hash {current.payload_hash}; epoch {current.epoch}; '
                            f'Git {self.store.settings.source_revision}; карточка действует до {expires.isoformat()}. '
                            'Эффект: JSON/Markdown в изолированном исполнителе, без внешних операций.')
                    delivery = self.enqueue(session, iid + ':card', text, markup)
                    card = TelegramCard(id=hashlib.sha256(token.encode()).hexdigest(), profile=self.profile,
                        delivery_id=delivery, task_id=current.id, version=current.version, payload_hash=current.payload_hash,
                        epoch=current.epoch, revision=self.store.settings.source_revision,
                        expires_at=expires)
                    session.add(card)
                    self.store.audit(session, 'telegram_card_created', 'owner', current.id,
                                     card_id=card.id, binding=self.card_binding(card))
                    row.state = 'DONE'
        elif kind == 'approve':
            with self.store.transaction() as session:
                card = session.get(TelegramCard, intent['card'])
                if not card or card.profile != self.profile:
                    raise Denied('telegram_card_unknown')
                task_id, version, expires = card.task_id, card.version, card.expires_at
            def consume(session, task):
                self.guard()
                card = session.get(TelegramCard, intent['card'])
                delivery = session.get(TelegramDelivery, card.delivery_id)
                anchored = session.execute(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_card_created',
                    Audit.event['card_id'].as_string() == card.id,
                    Audit.event['binding'].as_string() == self.card_binding(card))).first()
                observed = session.execute(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_delivery_observed',
                    Audit.event['delivery_id'].as_string() == delivery.id,
                    Audit.event['message_id'].as_integer() == intent['message_id'],
                    Audit.event['state'].as_string() == 'SENT')).first()
                if (card.consumed_update is not None or card.expires_at <= self.store.now(session)
                        or card.version != task.version or card.payload_hash != task.payload_hash
                        or card.epoch != task.epoch or card.epoch != session.get(Control, 1).epoch
                        or card.revision != self.store.settings.source_revision
                        or delivery.state != 'SENT' or delivery.message_id != intent['message_id']
                        or task.payload['kind'] != 'approved_render' or not anchored or not observed):
                    raise Denied('telegram_card_stale_or_used')
                card.consumed_update = iid
                self.finish(session, iid, 'Синтетический тест подтверждён. Ожидаем проверяемый результат.')
                self.store.audit(session, 'telegram_card_consumed', 'owner', task.id, version=task.version)
            self.store.approve('owner', task_id, version, _scope_installer=consume, _deadline=expires)
        elif kind in {'cancel_experiment', 'cancel_recovery'}:
            from .telegram_experiment_cancel import apply
            apply(scope, iid)
        elif kind == 'cancel':
            self.store.cancel('owner', intent['task_id'], _scope_installer=lambda session, task:
                              self.finish(session, iid, 'Намерение отмены сохранено; фактическая остановка проверяется.'))
        elif kind == 'stop':
            self.store.halt('owner', _scope_installer=lambda session, control:
                            self.finish(session, iid, 'Новые запуски остановлены; активные исполнения требуют сверки.'))
        elif kind in {'resume_request', 'resume_confirm'}:
            from .telegram_control import issue, confirm
            with self.store.transaction() as session:
                self.guard()
                self.store.check_audit(session)
                row = session.get(TelegramInbox, iid)
                if row.state == 'DONE':
                    return {'inbox_id': iid, 'state': row.state, 'task_id': row.task_id}
                anchor = session.execute(select(Audit).where(
                    Audit.event['kind'].as_string() == 'telegram_update_received',
                    Audit.event['profile'].as_string() == self.profile,
                    Audit.event['update_id'].as_string() == iid.rsplit(':', 1)[1],
                    Audit.event['intent_hash'].as_string() == digest(intent),
                    Audit.event['revision'].as_string() == self.store.settings.source_revision)).first()
                if row.state != 'RECEIVED' or row.fingerprint != digest(intent) or row.intent != intent or not anchor:
                    raise Denied('telegram_control_intent_integrity_or_source_changed')
                if kind == 'resume_request':
                    issue(self, session, iid)
                else:
                    confirm(self, session, iid, intent)
        elif kind == 'assign':
            from .project_inbox import classify, PROJECTS
            from .telegram_project_picker import verify
            if 'picker_callback' in intent:
                with self.store.transaction() as session:
                    self.store.check_audit(session)
                    verify(self, session, intent)
            def confirm(session, event):
                self.guard()
                row = session.get(TelegramInbox, iid)
                if row.state == 'DONE':
                    return
                if row.state != 'RECEIVED':
                    raise Denied('telegram_assignment_not_pending')
                if 'picker_callback' in intent:
                    verify(self, session, intent)
                label = dict(PROJECTS).get(event['project_id'], 'Не распределён')
                self.finish(session, iid, f'Запрос №{intent["number"]}: {label}. Версия назначения {event["version"]}. '
                            'Выбор проекта сохранён; выполнение не запускалось.')
            try:
                classify(self.store, 'owner', self.profile + ':' + intent['number'], intent['project_id'],
                         intent['version'], str(uuid5(NAMESPACE_URL, 'acc:telegram-project:' + iid)), _scope_installer=confirm)
            except Denied as error:
                if 'picker_callback' not in intent or str(error) != 'project_assignment_stale_version':
                    raise
                with self.store.transaction() as session:
                    self.guard()
                    self.store.check_audit(session)
                    verify(self, session, intent)
                    row = session.get(TelegramInbox, iid)
                    if row.state != 'DONE':
                        if row.state != 'RECEIVED':
                            raise Denied('telegram_assignment_not_pending')
                        self.finish(session, iid, 'Проект не изменён: карточка устарела. '
                                    f'Откройте /request {intent["number"]}, чтобы выбрать проект заново.')
        elif kind == 'calendar_create':
            from .telegram_calendar import create_card
            create_card(self, iid, intent)
        elif kind == 'calendar_decide':
            from .telegram_calendar import apply_decision
            apply_decision(self, iid, intent)
        elif kind == 'calendar_voice':
            from .telegram_calendar_voice import capture
            with self.store.transaction() as session:
                self.store.check_audit(session)
                capture(self, session, iid, intent)
        elif kind == 'voice_request':
            from .telegram_voice_requests import capture
            with self.store.transaction() as session:
                self.store.check_audit(session)
                capture(self, session, iid, intent)
        elif kind == 'voice_confirm':
            from .telegram_voice_transcripts import decide
            decide(self, iid, intent)
        elif kind in {'tasks', 'status', 'requests', 'request', 'projects', 'attention', 'reminders',
                      'calendar_list', 'voice', 'system', 'project', 'plan_review', 'coding_plan', 'readiness', 'experiment',
                      'watch_experiment', 'unwatch_experiment', 'recovery', 'watch_recovery', 'unwatch_recovery'}:
            with self.store.transaction() as session:
                self.store.check_audit(session)
                row = session.get(TelegramInbox, iid)
                if row.state == 'DONE':
                    return {'inbox_id': iid, 'state': row.state, 'task_id': row.task_id}
                if row.state != 'RECEIVED':
                    raise Denied('telegram_query_not_pending')
                suffix = '\n\nРабота по реальной бизнес-задаче не выполнялась.'
                control = session.get(Control, 1)
                if control.halted or control.recovery:
                    suffix += '\n\nНовые запуски остановлены; чтение статуса не возобновляет выполнение.'
                if kind == 'readiness':
                    from .telegram_readiness import reply as readiness_reply
                    reply = readiness_reply(self, session)
                elif kind in {'experiment', 'recovery'}:
                    from .telegram_experiment import reply as experiment_reply
                    reply = experiment_reply(scope, session)
                elif kind in {'watch_experiment', 'unwatch_experiment', 'watch_recovery', 'unwatch_recovery'}:
                    from .telegram_experiment_watch import change
                    reply = change(scope, session, iid, kind in {'watch_experiment', 'watch_recovery'})
                elif kind == 'coding_plan':
                    from .telegram_coding import plan
                    reply = plan()
                elif kind == 'projects':
                    from .telegram_requests import projects_reply
                    reply = projects_reply(self, session)
                elif kind == 'project':
                    from .telegram_requests import project_reply
                    reply = project_reply(session, intent['project_id'])
                elif kind == 'attention':
                    from .attention import telegram_reply
                    reply = telegram_reply(self.store, session)
                elif kind == 'reminders':
                    from .attention_schedule import telegram_reply
                    reply = telegram_reply(session)
                elif kind == 'calendar_list':
                    from .telegram_calendar import list_reply
                    reply = list_reply(session, self.profile)
                elif kind == 'voice':
                    from .telegram_voice_requests import reply as voice_reply
                    reply = voice_reply(session, self.profile)
                elif kind == 'system':
                    from .telegram_system import reply as system_reply
                    reply = system_reply(session, self.profile)
                elif kind == 'plan_review':
                    from .telegram_plan_review import reply as plan_reply
                    reply = plan_reply(self, session, intent, suffix)
                    reply += '\n/assign номер project-id версия — выбрать проект; none — снять назначение. '
                    reply += 'Номер и текущая версия: /request номер. AI-разработка проектов не подключена.'
                elif kind in {'requests', 'request'}:
                    reply = request_reply(self, session, intent, suffix=suffix)
                else:
                    # Scope is derived from the durable F1 request key, never from a
                    # supplied UUID alone or a mutable inbox task_id link alone.
                    query = self.scoped_tasks()
                    if kind == 'status':
                        query = query.where(Task.id == intent['task_id'])
                    tasks = session.execute(query.order_by(Task.created_at.desc(), Task.id.desc()).limit(5)).scalars().all()
                    if not tasks:
                        reply = ('Синтетических тестов в этом Telegram-подключении пока нет.' if kind == 'tasks'
                                 else 'Задача не найдена среди синтетических тестов этого Telegram-подключения.')
                    else:
                        reply = ('Последние синтетические тесты (до 5):\n\n' if kind == 'tasks' else '')
                        reply += '\n\n'.join(self.task_summary(session, task, compact=True) if kind == 'tasks'
                                             else self.task_summary(session, task) for task in tasks)
                from .telegram_project_picker import saved_version, keyboard as picker_keyboard, issue
                version = saved_version(self, session, intent['number']) if kind == 'request' else None
                markup = picker_keyboard(intent['number'], version) if version is not None else None
                if markup and len(canonical({'chat_id': self.owner, 'text': reply + suffix,
                                             'reply_markup': markup}).encode()) > 8192:
                    # Preserve the full readback and the existing transport limit.
                    self.finish(session, iid, reply + suffix)
                    delivery = self.enqueue(session, iid + ':picker',
                        f'Выберите проект запроса №{intent["number"]}. Выполнение не запускалось.', markup)
                else:
                    delivery = scope.finish(session, iid, reply + suffix, markup)
                if markup:
                    issue(self, session, delivery, intent['number'], version)
        else:
            with self.store.transaction() as session:
                self.store.check_audit(session)
                if kind == 'capture':
                    row = session.get(TelegramInbox, iid)
                    if row.state == 'NEEDS_PLANNING':
                        return {'inbox_id': iid, 'state': row.state, 'task_id': row.task_id}
                    if row.state != 'RECEIVED':
                        raise Denied('telegram_capture_not_pending')
                    self.check_text(intent.get('text'))
                    if not intent['text'].strip():
                        raise Denied('telegram_empty_request')
                    self.guard()
                    row.state = 'NEEDS_PLANNING'
                    from .telegram_project_picker import keyboard as picker_keyboard, issue
                    number = iid.rsplit(':', 1)[1]
                    delivery = self.enqueue(session, iid + ':reply', capture_receipt(iid), picker_keyboard(number, 0))
                    issue(self, session, delivery, number, 0)
                else:
                    row = session.get(TelegramInbox, iid)
                    if row.state == 'DONE':
                        return {'inbox_id': iid, 'state': row.state, 'task_id': row.task_id}
                    if row.state != 'RECEIVED':
                        raise Denied('telegram_help_not_pending')
                    self.finish(session, iid, 'Выберите кнопку меню или напишите запрос обычным текстом. '
                        'Текст сохраняется и ожидает планирования.\n\n'
                        '/menu — показать меню; /demo текст — синтетический тест с подтверждением; '
                        '/requests — сохранённые запросы; /requests project-id — очередь проекта; '
                        '/request номер — открыть запрос; '
                        '/plan номер — посмотреть сохранённый черновик плана; '
                        '/projects — проекты и назначение; /project project-id — подключение и границы; '
                        '/attention — центр внимания; /reminders — расписание сводок; '
                        '/voice — голосовые поручения до расшифровки; /system — роли и состояние компонентов; '
                        '/readiness — состояние Commander и условия первого AI-запуска; '
                        '/experiment — состояние и результат первого AI-эксперимента; '
                        '/prepare_experiment — подготовить этот тест без запуска и расходов; '
                        '/authorize_experiment — показать условия отдельного платного разрешения; '
                        '/cancel_experiment — запросить отмену этой задачи; '
                        '/watch_experiment — включить уведомления; /unwatch_experiment — отключить; '
                        '/recovery — отдельный восстановительный тест; /prepare_recovery — подготовить; '
                        '/authorize_recovery — условия платного разрешения; /cancel_recovery — отмена; '
                        '/watch_recovery, /unwatch_recovery — уведомления; '
                        '/coding_plan — план тестового разработчика; /coding_demo — запустить mock-упражнение; '
                        '/tasks — последние тесты; /status UUID — состояние теста; /cancel UUID; /stop; '
                        '/resume — запросить снятие обычной остановки с подтверждением. '
                        'Обычное голосовое или голосовое с подписью /task сохраняется как поручение; '
                        'подпись /calendar направляет его в календарь. Файл не скачивается до доверенной расшифровки. '
                        'Обычные запросы ожидают планирования; '
                        'AI-эксперимент требует отдельного разрешения. Условия: /readiness.', keyboard())
        with self.store.transaction() as session:
            row = session.get(TelegramInbox, iid)
            return {'inbox_id': iid, 'state': row.state, 'task_id': row.task_id}

    def scoped_tasks(self):
        from .telegram_coding import exercise
        fixed = exercise()
        accepted = select(Audit).where(
            Audit.event['kind'].as_string() == 'telegram_coding_accepted',
            Audit.event['actor'].as_string() == 'owner',
            Audit.event['task_id'].as_string() == Task.id,
            Audit.event['profile'].as_string() == self.profile,
            Audit.event['inbox_id'].as_string() == TelegramInbox.id,
            Audit.event['request_fingerprint'].as_string() == TelegramInbox.fingerprint,
            Audit.event['payload_hash'].as_string() == digest(fixed)).exists()
        return select(Task).join(TelegramInbox,
            (TelegramInbox.task_id == Task.id) & (Task.request_key == 'owner:tg:' + TelegramInbox.id)).where(
                TelegramInbox.profile == self.profile, TelegramInbox.state == 'DONE', Task.owner_role == 'owner',
                or_(and_(TelegramInbox.intent['kind'].as_string() == 'demo',
                         Task.payload['kind'].as_string() == 'approved_render'),
                    and_(TelegramInbox.intent == {'kind': 'coding_demo'},
                         TelegramInbox.fingerprint == digest({'kind': 'coding_demo'}),
                         Task.payload == fixed, Task.payload_hash == digest(fixed), accepted)))

    def confirmed_result(self, session, task):
        return bool(task.state == 'SUCCEEDED' and isinstance(task.artifact, str)
            and hashlib.sha256(task.artifact.encode()).hexdigest() == task.artifact_hash
            and session.execute(select(Audit).where(
                Audit.event['kind'].as_string() == 'verified',
                Audit.event['task_id'].as_string() == task.id,
                Audit.event['actor'].as_string() == 'verifier',
                Audit.event['artifact_hash'].as_string() == task.artifact_hash,
                Audit.event['fence'].as_integer() == task.fence,
                Audit.event['revision'].as_string() == self.store.settings.source_revision)).first())

    def task_summary(self, session, task, *, compact=False):
        states = {
            'WAITING_APPROVAL': 'Ожидает отдельного подтверждения синтетического теста.',
            'READY': 'Ожидает исполнителя.',
            'RUNNING': 'Выполняется.',
            'VERIFYING': 'Результат проверяется.',
            'CANCEL_REQUESTED': 'Намерение отмены сохранено; фактическая остановка ещё не подтверждена.',
            'CANCELLED': 'В записи задачи: отменена.',
            'RECONCILING': 'Результат неопределён; нужна сверка. Повторный запуск не разрешён этой командой.',
            'SECURITY_BLOCKED': 'Выполнение заблокировано проверкой безопасности.',
            'FAILED': 'Тест не завершился успешно.',
        }
        summary = states.get(task.state, 'Неизвестное состояние; нужна сверка.')
        if task.state == 'SUCCEEDED':
            summary = ('Результат независимо проверен; SHA-256 ' + task.artifact_hash if self.confirmed_result(session, task)
                       else 'Успех не подтверждён; нужна сверка состояния.')
            if task.payload['kind'] == 'coding_synthetic':
                from .telegram_coding import summary as coding_summary
                summary = coding_summary(self, session, task, compact=compact)
        if task.state == 'RUNNING' and (task.lease_until is None or task.lease_until <= self.store.now(session)):
            summary = 'Lease истёк или отсутствует; текущее выполнение не подтверждено, нужна сверка.'
        # Only fixed explanations leave the control plane: no arbitrary reason,
        # payload, artifact, provider output, credentials or repository content.
        reasons = {'budget_limit': 'Исчерпан лимит бюджета.', 'attempt_limit': 'Исчерпан лимит попыток.',
                   'expired_lease': 'Истёк срок полномочий исполнителя.',
                   'isolation_policy_mismatch': 'Изоляция исполнителя не соответствует требованиям.'}
        if task.reason in reasons:
            summary += ' ' + reasons[task.reason]
        label = 'Тестовый разработчик (mock)' if task.payload['kind'] == 'coding_synthetic' else 'Синтетический тест'
        return f'{label} {task.id}\n{summary}\nПодробнее: /status {task.id}'

    def collect_results(self):
        with self.store.transaction() as session:
            self.store.check_audit(session)
            for task in session.execute(self.scoped_tasks()).scalars():
                if task.state in {'SUCCEEDED', 'FAILED', 'CANCELLED', 'RECONCILING', 'SECURITY_BLOCKED'}:
                    if task.payload['kind'] == 'coding_synthetic':
                        text = task.state + '\n' + self.task_summary(session, task)
                    else:
                        text = f'Синтетический тест {task.id}: {task.state}. '
                        verified = self.confirmed_result(session, task)
                        text += ('Результат независимо проверен; SHA-256 ' + str(task.artifact_hash)
                                 if verified else 'Успех не подтверждён; нужна сверка состояния.')
                    text += ' Работа по реальной бизнес-задаче не выполнялась.'
                    self.enqueue(session, f'task:{task.id}:{task.version}:{task.state}', text)
            from .telegram_experiment_watch import collect
            collect(self, session)
            collect(RecoveryBridge(self), session)
            from .attention_schedule import collect as collect_attention
            collect_attention(self, session)
            from .telegram_calendar import collect_reminders
            collect_reminders(self, session)

    def deliver_one(self):
        self.guard()
        with self.store.transaction() as session:
            self.store.check_audit(session)
            row = session.execute(select(TelegramDelivery).join(Audit,
                Audit.event['delivery_id'].as_string() == TelegramDelivery.id).where(
                    TelegramDelivery.profile == self.profile, TelegramDelivery.state == 'NEW',
                    Audit.event['kind'].as_string() == 'telegram_delivery_queued')
                .order_by(Audit.sequence).limit(1)).scalar_one_or_none()
            if not row:
                return None
            row.state, row.deadline = 'SENDING', self.store.now(session) + timedelta(seconds=30)
            oid, body = row.id, dict(row.body)
            anchored = session.execute(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_delivery_queued',
                Audit.event['delivery_id'].as_string() == oid,
                Audit.event['request_hash'].as_string() == digest(body))).first()
            if (not anchored or body.get('chat_id') != self.owner
                    or not isinstance(body.get('text'), str) or not 1 <= len(body['text']) <= 4096
                    or set(body) - {'chat_id', 'text', 'reply_markup'}):
                raise Denied('telegram_delivery_scope_or_integrity_invalid')
            self.store.audit(session, 'telegram_delivery_intent', 'system', delivery_id=oid)
        try:
            result = self.client.call('sendMessage', body)
            if (not isinstance(result, dict) or type(result.get('message_id')) is not int
                    or result['message_id'] <= 0 or result.get('chat', {}).get('id') != self.owner):
                raise ValueError('telegram_message_receipt_invalid')
        except Exception:
            with self.store.transaction() as session:
                row = session.get(TelegramDelivery, oid)
                row.state = 'UNCERTAIN'
                self.store.audit(session, 'telegram_delivery_uncertain', 'system', delivery_id=oid)
            return {'id': oid, 'state': 'UNCERTAIN'}
        with self.store.transaction() as session:
            row = session.get(TelegramDelivery, oid)
            if row.state != 'SENDING' or row.deadline <= self.store.now(session):
                row.state = 'UNCERTAIN'
            else:
                row.state, row.message_id = 'SENT', result['message_id']
            self.store.audit(session, 'telegram_delivery_observed', 'system', delivery_id=oid,
                             state=row.state, message_id=row.message_id)
            return {'id': oid, 'state': row.state}

    def recover(self):
        with self.store.transaction() as session:
            self.store.check_audit(session)
            rows = session.execute(select(TelegramDelivery).where(TelegramDelivery.profile == self.profile,
                TelegramDelivery.state == 'SENDING', TelegramDelivery.deadline <= self.store.now(session))).scalars()
            for row in rows:
                row.state = 'UNCERTAIN'
                self.store.audit(session, 'telegram_delivery_recovery_uncertain', 'system', delivery_id=row.id)

    def resume_pending(self):
        with self.store.transaction() as session:
            self.store.check_audit(session)
            rows = session.execute(select(TelegramInbox).where(TelegramInbox.profile == self.profile,
                TelegramInbox.state == 'RECEIVED').order_by(TelegramInbox.created_at).limit(20)).scalars()
            pending = []
            for row in rows:
                anchor = session.execute(select(Audit).where(
                    Audit.event['kind'].as_string() == 'telegram_update_received',
                    Audit.event['profile'].as_string() == self.profile,
                    Audit.event['update_id'].as_string() == row.id.split(':')[-1],
                    Audit.event['intent_hash'].as_string() == digest(row.intent),
                    Audit.event['revision'].as_string() == self.store.settings.source_revision)).first()
                if row.fingerprint != digest(row.intent) or not anchor:
                    raise Denied('telegram_pending_integrity_or_source_revision_changed')
                pending.append((row.id, row.intent))
        for iid, intent in pending:
            try:
                self._apply_pending(iid, intent)
            except Denied as error:
                self.guard()
                if 'capacity' in str(error):
                    raise
                with self.store.transaction() as session:
                    self.store.check_audit(session)
                    row = session.get(TelegramInbox, iid)
                    if row.state == 'RECEIVED':
                        row.state = 'REJECTED'
                        self.store.audit(session, 'telegram_pending_rejected', 'owner', inbox_id=iid)

    def acknowledge(self, update_id, query_id):
        key = token_fingerprint(self.profile + ':' + update_id)
        with self.store.transaction() as session:
            self.store.check_audit(session)
            seen = session.execute(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_callback_ack_intent',
                                                       Audit.event['ack_id'].as_string() == key)).first()
            if seen:
                return
            self.guard()
            self.store.audit(session, 'telegram_callback_ack_intent', 'system', ack_id=key)
        result = 'UNCERTAIN'
        try:
            if self.client.call('answerCallbackQuery', {'callback_query_id': query_id}) is True:
                result = 'ACKNOWLEDGED'
        except Exception:
            pass  # Never undo a committed approval or repeat an uncertain acknowledgement.
        with self.store.transaction() as session:
            self.store.check_audit(session)
            self.store.audit(session, 'telegram_callback_ack_result', 'system', ack_id=key, state=result)

    def poll_once(self, timeout=0):
        self.guard()
        self.recover()
        self.resume_pending()
        with self.store.transaction() as session:
            self.store.check_audit(session)
            rows = session.execute(select(TelegramInbox).where(TelegramInbox.profile == self.profile)).scalars().all()
            pending = sorted((r for r in rows if r.state == 'RECEIVED'), key=lambda r: int(r.id.split(':')[-1]))
            recent = [r for r in rows if r.created_at >= self.store.now(session) - timedelta(days=7)]
            offset = min(int(r.id.split(':')[-1]) for r in pending) if pending else max(
                (int(r.id.split(':')[-1]) + 1 for r in recent), default=0)
            reply_pending = session.scalar(select(select(TelegramDelivery.id).where(
                TelegramDelivery.profile == self.profile, TelegramDelivery.state == 'NEW').exists()))
        # Check inbound controls before sending, but do not long-poll while a
        # durable reply is waiting. Sending first could stall a queued /stop.
        updates = self.client.call('getUpdates', {'offset': offset, 'limit': 20, 'timeout': 0 if reply_pending else timeout,
                                                 'allowed_updates': ['message', 'callback_query']})
        if not isinstance(updates, list) or len(updates) > 20:
            raise Denied('telegram_batch_invalid')
        previous = offset - 1
        for update in updates:
            uid = update.get('update_id') if isinstance(update, dict) else None
            if type(uid) is not int or not previous <= uid < 2**53 or uid < offset:
                raise Denied('telegram_batch_order_invalid')
            previous = uid
            try:
                self.receive(update)
                if isinstance(self.client, ConfiguredTelegramHTTP) and isinstance(update.get('callback_query'), dict):
                    self.acknowledge(str(uid), update['callback_query']['id'])
            except Denied:
                self.guard()  # Revocation/leadership loss must not discard a pending command.
                # Rejected records retain no external text, files or sender metadata.
                with self.store.transaction() as session:
                    self.store.check_audit(session)
                    iid = self.profile + ':' + str(uid)
                    row = session.get(TelegramInbox, iid)
                    if row is None:
                        if session.scalar(select(func.count()).select_from(TelegramInbox)) >= 1000:
                            raise Denied('telegram_inbox_capacity')
                        session.add(TelegramInbox(id=iid, profile=self.profile, fingerprint=digest({'rejected': uid}),
                            intent={'kind': 'rejected'}, state='REJECTED', created_at=self.store.now(session)))
                    elif row.state == 'RECEIVED':
                        row.state = 'REJECTED'
                    self.store.audit(session, 'telegram_update_rejected', 'unauthenticated', update_id=uid)
        self.guard()
        self.collect_results()
        return [result for _ in range(20) if (result := self.deliver_one()) is not None]
