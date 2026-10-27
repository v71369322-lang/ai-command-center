"""Telegram intents reuse F1 authority; external transport is separately scoped."""
from datetime import timedelta
import hashlib
import json
import re
import secrets
from uuid import UUID

import httpx
from sqlalchemy import select, func

from .api import Command
from .models import TelegramInbox, TelegramDelivery, TelegramCard, Control, Audit
from .store import Denied, digest
from .telegram_transport import ConfiguredTelegramHTTP, token_fingerprint


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
            if (not isinstance(token, str) or not re.fullmatch(r'tg:[A-Za-z0-9_-]{32}', token)
                    or type(message.get('message_id')) is not int or message['message_id'] <= 0):
                raise Denied('telegram_callback_invalid')
            intent = {'kind': 'approve', 'card': hashlib.sha256(token[3:].encode()).hexdigest(),
                      'message_id': message.get('message_id')}
            if isinstance(self.client, ConfiguredTelegramHTTP):
                query_id = callback.get('id')
                if (not isinstance(query_id, str) or not 1 <= len(query_id) <= 128
                        or self.client.sensitive(query_id)):
                    raise Denied('telegram_callback_invalid')
                intent['callback_query_id'] = query_id
            return str(uid), intent
        value = message.get('text')
        if not isinstance(value, str) or not 1 <= len(value.encode()) <= 2000:
            raise Denied('telegram_text_only')
        known = [*self.store.settings.identities.values(), self.store.settings.redis_password,
                 self.store.settings.database_url.password]
        if (any(v and v in value for v in known)
                or (isinstance(self.client, ConfiguredTelegramHTTP) and self.client.sensitive(value))
                or re.search(r'PRIVATE KEY|\bsk-[A-Za-z0-9_-]{20,}|\bgh[pousr]_[A-Za-z0-9]{20,}|\b[0-9]{6,20}:[A-Za-z0-9_-]{30,128}', value)):
            raise Denied('telegram_secret_content_forbidden')
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
        if value in {'/start', '/help'}:
            return str(uid), {'kind': 'help'}
        return str(uid), {'kind': 'capture', 'text': value.removeprefix('/task ')}

    def finish(self, session, iid, text):
        self.guard()
        self.store.check_audit(session)
        row = session.get(TelegramInbox, iid)
        if row.state == 'DONE':
            raise Denied('telegram_update_already_committed')
        row.state = 'DONE'
        self.enqueue(session, iid + ':reply', text)

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
                if session.scalar(select(func.count()).select_from(TelegramInbox)) >= 1000:
                    raise Denied('telegram_inbox_capacity')
                session.add(TelegramInbox(id=iid, profile=self.profile, fingerprint=digest(intent), intent=intent,
                                         state='RECEIVED', created_at=self.store.now(session)))
                self.store.audit(session, 'telegram_update_received', 'owner', update_id=update_id, profile=self.profile,
                                 intent_hash=digest(intent))
        return self._apply_pending(iid, intent)

    def _apply_pending(self, iid, intent):
        self.guard()
        kind = intent['kind']
        if kind == 'demo':
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
        elif kind == 'cancel':
            self.store.cancel('owner', intent['task_id'], _scope_installer=lambda session, task:
                              self.finish(session, iid, 'Намерение отмены сохранено; фактическая остановка проверяется.'))
        elif kind == 'stop':
            self.store.halt('owner', _scope_installer=lambda session, control:
                            self.finish(session, iid, 'Новые запуски остановлены; активные исполнения требуют сверки.'))
        else:
            with self.store.transaction() as session:
                self.store.check_audit(session)
                if kind == 'capture':
                    session.get(TelegramInbox, iid).state = 'NEEDS_PLANNING'
                    self.enqueue(session, iid + ':reply', 'Запрос сохранён. AI-планирование ещё не подключено; бизнес-действия не выполнялись.')
                else:
                    self.finish(session, iid, 'Текст — сохранить запрос; /demo текст — синтетический тест с подтверждением; /cancel UUID; /stop. Голос и реальные AI пока отключены.')
        with self.store.transaction() as session:
            row = session.get(TelegramInbox, iid)
            return {'inbox_id': iid, 'state': row.state, 'task_id': row.task_id}

    def collect_results(self):
        with self.store.transaction() as session:
            self.store.check_audit(session)
            rows = session.execute(select(TelegramInbox).where(TelegramInbox.profile == self.profile,
                                    TelegramInbox.task_id.is_not(None))).scalars()
            for row in rows:
                task = self.store.task(session, row.task_id)
                if task.state in {'SUCCEEDED', 'FAILED', 'CANCELLED', 'RECONCILING', 'SECURITY_BLOCKED'}:
                    text = f'Синтетический тест {task.id}: {task.state}. '
                    verified = (task.state == 'SUCCEEDED' and isinstance(task.artifact, str)
                        and hashlib.sha256(task.artifact.encode()).hexdigest() == task.artifact_hash
                        and session.execute(select(Audit).where(
                            Audit.event['kind'].as_string() == 'verified',
                            Audit.event['task_id'].as_string() == task.id,
                            Audit.event['actor'].as_string() == 'verifier',
                            Audit.event['artifact_hash'].as_string() == task.artifact_hash,
                            Audit.event['fence'].as_integer() == task.fence,
                            Audit.event['revision'].as_string() == self.store.settings.source_revision)).first())
                    text += ('Результат независимо проверен; SHA-256 ' + str(task.artifact_hash)
                             if verified else 'Успех не подтверждён; нужна сверка состояния.')
                    text += ' Работа по реальной бизнес-задаче не выполнялась.'
                    self.enqueue(session, f'task:{task.id}:{task.version}:{task.state}', text)

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
        updates = self.client.call('getUpdates', {'offset': offset, 'limit': 20, 'timeout': timeout,
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
