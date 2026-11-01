"""Explicit paid-experiment consent over the existing local F1 grant path."""
from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets

from sqlalchemy import select

from .coding.first_experiment import CAP, RECOVERY_ID
from .coding.recovery import RecoveryExperiment
from .coding.gateway import Gateway
from .coding.integration_config import IntegrationConfig
from .models import Audit, Control, ExternalGrant, TelegramDelivery, TelegramInbox
from .store import Denied, canonical, digest
from .telegram_experiment import rub, snapshot, task_record
from .telegram_experiment_scope import experiment_id, key

ISSUED = 'telegram_experiment_approval_issued'
CONSUMED = 'telegram_experiment_approval_consumed'
LABEL = 'Разрешить платный AI-тест'
TERM_KEYS = {'task_id', 'version', 'payload_hash', 'epoch', 'budget', 'seconds', 'profile_hash', 'config_fingerprint'}


def parse_callback(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:fx|rx):[A-Za-z0-9_-]{32}', value):
        raise Denied('experiment_approval_callback_invalid')
    return {'kind': 'recovery_authorize_confirm' if value.startswith('rx:') else 'experiment_authorize_confirm',
            'card': hashlib.sha256(value[3:].encode()).hexdigest()}


def keyboard(token, *, recovery=False):
    return {'inline_keyboard': [[{'text': 'Разрешить платный восстановительный тест' if recovery else LABEL,
                                 'callback_data': ('rx:' if recovery else 'fx:') + token}]]}


def allowed_markup(value):
    try:
        data = value['inline_keyboard'][0][0]['callback_data']
        parse_callback(data)
        return canonical(value) == canonical(keyboard(data[3:], recovery=data.startswith('rx:')))
    except (Denied, KeyError, IndexError, TypeError):
        return False


def configuration():
    try:
        return IntegrationConfig.load()
    except (OSError, ValueError):
        raise Denied('experiment_approval_profile_unavailable') from None


def terms(bridge, session, config, *, state='WAITING_APPROVAL', check_grants=True):
    control = session.get(Control, 1)
    task, _ = task_record(bridge, session)
    if task is None:
        raise Denied('experiment_approval_task_missing')
    bridge.store.check_task_revision(session, task)
    if control.halted or control.recovery or task.epoch != control.epoch or task.state != state:
        raise Denied('experiment_approval_task_ineligible')
    if (config.mode != 'live' or not config.first_experiment or not config.connected()
            or config.first_experiment.id != experiment_id(bridge)
            or not 1 <= len(config.synthetic_repository) <= 140):
        raise Denied('experiment_approval_live_profile_required')
    if not config.tariff or not config.tariff.confirmed or not config.budget_evidence:
        raise Denied('budget_unconfirmed')
    budget = config.tariff.maximum() * config.first_experiment.call_limit
    if not 0 < budget <= min(CAP, config.daily_nano_rub, config.monthly_nano_rub):
        raise Denied('experiment_approval_capacity')
    config.first_experiment.validate_scope(config, task.payload['coding'], budget, bridge.store.now(session),
                                           final_confirmation=True)  # Validation only, no grant or consent inferred.
    if isinstance(config.first_experiment, RecoveryExperiment):
        config.first_experiment.verify_parent(bridge.store, session, config)
    if check_grants and session.scalar(select(ExternalGrant).where(
            ExternalGrant.document['experiment_id'].as_string() == experiment_id(bridge),
            ExternalGrant.document['mode'].as_string() == 'live').limit(1)):
        raise Denied('first_experiment_already_bound')
    return task, {'task_id': task.id, 'version': task.version, 'payload_hash': task.payload_hash,
                  'epoch': control.epoch, 'budget': budget, 'seconds': 120,
                  'profile_hash': digest(config.model_dump()),
                  'config_fingerprint': digest({'config': config.model_dump(), 'references': config.credential_files})}


def receipt(bridge, session, iid, kind):
    row = session.get(TelegramInbox, iid)
    if (not row or row.profile != bridge.profile or row.state != 'RECEIVED' or not isinstance(row.intent, dict)
            or row.intent.get('kind') != kind or row.fingerprint != digest(row.intent)):
        raise Denied('experiment_approval_receipt_invalid')
    received = session.scalar(select(Audit).where(
        Audit.event['kind'].as_string() == 'telegram_update_received',
        Audit.event['actor'].as_string() == 'owner', Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['update_id'].as_string() == iid.removeprefix(bridge.profile + ':'),
        Audit.event['intent_hash'].as_string() == digest(row.intent),
        Audit.event['revision'].as_string() == bridge.store.settings.source_revision).order_by(Audit.sequence).limit(1))
    if not received:
        raise Denied('experiment_approval_receipt_invalid')
    return row, received


def issue(bridge, session, iid):
    row, received = receipt(bridge, session, iid, key(bridge, 'experiment_authorize_request'))
    if row.intent != {'kind': key(bridge, 'experiment_authorize_request')} or row.task_id is not None:
        raise Denied('experiment_approval_receipt_invalid')
    expires = datetime.fromisoformat(received.event['time']) + timedelta(seconds=120)
    if not expires - timedelta(seconds=120) <= bridge.store.now(session) < expires:
        return bridge.finish(session, iid, 'Запрос подтверждения истёк. Отправьте /authorize_experiment заново.')
    config = configuration()
    try:
        snapshot(bridge, session)  # Existing ledger integrity; no Gateway/client construction.
        task, document = terms(bridge, session, config)
    except Denied:
        return bridge.finish(session, iid, 'Подтверждение платного AI-теста пока недоступно. '
                             'Нужны подготовленная задача, открытый приём и действующий AI-профиль со всеми условиями. '
                             'Проверить: /experiment и /readiness. Подготовить задачу: /prepare_experiment. '
                             'Расходы и запуск этой командой не разрешены.')
    token = secrets.token_urlsafe(24)
    body = ('Разрешить первый платный AI-тест?\n'
            f'Задача: {task.id}.\n'
            'Исправить сумму положительных чисел только в calculator.py.\n'
            f'Модель: {config.first_experiment.model}. Репозиторий: {config.synthetic_repository}.\n'
            f'Лимит двух вызовов: {rub(document["budget"])}. До двух AI-вызовов и одного исправления, '
            'независимая проверка и Draft PR; без merge, CRM и повторного запуска.\n'
            'Это расчётный лимит по подтверждённому профилю, а не гарантия отсечения списаний провайдером. '
            'Разрешение на запуск действует до 120 секунд после подтверждения; условия перепроверяются перед действиями.\n'
            f'Подтвердить до {expires.astimezone(timezone.utc).isoformat()} (UTC). '
            'Кнопка ниже разрешает реальные AI-вызовы и публикацию Draft PR в указанном тестовом репозитории.')
    if experiment_id(bridge) == RECOVERY_ID:
        parent = config.first_experiment.verify_parent(bridge.store, session, config)
        body = (f'Разрешить отдельный платный восстановительный тест?\nЗадача: {task.id}.\n'
                f'Исходная задача: {parent["task_id"]}; её ошибка и расход сохранены.\n'
                f'Учтённый расход исходной задачи: {rub(parent["actual_nano_rub"])}.\n'
                f'Модель: {config.first_experiment.model}. Репозиторий: {config.synthetic_repository}.\n'
                f'Один AI-вызов, без исправлений и повторов. Лимит новой задачи: {rub(document["budget"])}.\n'
                f'Сумма прежнего расхода и нового резерва: {rub(parent["actual_nano_rub"] + document["budget"])}.\n'
                'Только calculator.py, независимая проверка и Draft PR; без merge и CRM.\n'
                'Это расчётный лимит, а не гарантия отсечения провайдером. Разрешение запуска — 120 секунд.\n'
                f'Подтвердить до {expires.astimezone(timezone.utc).isoformat()} (UTC).\n'
                'Кнопка ниже разрешает реальные AI-вызовы и публикацию Draft PR в указанном тестовом репозитории.')
    delivery = bridge.finish(session, iid, body, keyboard(token, recovery=experiment_id(bridge) == RECOVERY_ID))
    bridge.store.audit(session, key(bridge, ISSUED), 'owner', task.id, profile=bridge.profile, delivery_id=delivery,
                       card=hashlib.sha256(token.encode()).hexdigest(), terms=document,
                       terms_hash=digest(document), expires_at=expires.isoformat(),
                       connection_digest=getattr(bridge.client, 'approved', bridge.profile))


def card(bridge, session, iid, intent):
    row, _ = receipt(bridge, session, iid, key(bridge, 'experiment_authorize_confirm'))
    if row.intent != intent or row.task_id is not None:
        raise Denied('experiment_approval_receipt_invalid')
    issued = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == key(bridge, ISSUED),
        Audit.event['actor'].as_string() == 'owner', Audit.event['profile'].as_string() == bridge.profile,
        Audit.event['card'].as_string() == intent['card']).limit(1))
    if not issued:
        raise Denied('experiment_approval_card_unknown')
    event, document = issued.event, issued.event.get('terms')
    if (not isinstance(document, dict) or set(document) != TERM_KEYS or digest(document) != event.get('terms_hash')
            or any(type(document.get(k)) is not int for k in ('version', 'epoch', 'budget', 'seconds'))
            or document['seconds'] != 120 or not 0 < document['budget'] <= CAP
            or event.get('task_id') != document['task_id']
            or event.get('revision') != bridge.store.settings.source_revision
            or event.get('connection_digest') != getattr(bridge.client, 'approved', bridge.profile)):
        raise Denied('experiment_approval_binding_invalid')
    delivery = session.get(TelegramDelivery, event.get('delivery_id'))
    if (not delivery or delivery.profile != bridge.profile or delivery.state != 'SENT'
            or delivery.message_id != intent['message_id'] or delivery.body.get('chat_id') != bridge.owner
            or not allowed_markup(delivery.body.get('reply_markup'))
            or parse_callback(delivery.body['reply_markup']['inline_keyboard'][0][0]['callback_data'])['kind']
            != key(bridge, 'experiment_authorize_confirm')
            or parse_callback(delivery.body['reply_markup']['inline_keyboard'][0][0]['callback_data'])['card'] != intent['card']
            or not session.scalar(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_delivery_queued',
                Audit.event['delivery_id'].as_string() == delivery.id,
                Audit.event['request_hash'].as_string() == digest(delivery.body)).limit(1))
            or not session.scalar(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_delivery_observed',
                Audit.event['delivery_id'].as_string() == delivery.id,
                Audit.event['message_id'].as_integer() == intent['message_id'],
                Audit.event['state'].as_string() == 'SENT').limit(1))):
        raise Denied('experiment_approval_card_not_observed')
    consumed = session.scalar(select(Audit).where(Audit.event['kind'].as_string() == key(bridge, CONSUMED),
        Audit.event['profile'].as_string() == bridge.profile, Audit.event['card'].as_string() == intent['card']).limit(1))
    return event, consumed


def current(bridge, session, event, config, *, state='WAITING_APPROVAL', check_grants=True):
    try:
        expires = datetime.fromisoformat(event['expires_at'])
        if expires.tzinfo is None or not expires - timedelta(seconds=120) <= bridge.store.now(session) < expires:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise Denied('experiment_approval_expired') from None
    _, proposed = terms(bridge, session, config, state=state, check_grants=check_grants)
    if proposed != event['terms']:
        raise Denied('experiment_approval_profile_or_task_changed')
    return expires


def confirm(bridge, iid, intent):
    with bridge.store.transaction() as session:
        bridge.guard()
        bridge.store.check_audit(session)
        prior = session.get(TelegramInbox, iid)
        if (prior and prior.profile == bridge.profile and prior.state == 'DONE'
                and prior.intent == intent and prior.fingerprint == digest(intent)):
            return
        event, consumed = card(bridge, session, iid, intent)
        if consumed:
            return bridge.finish(session, iid, 'Это разрешение уже использовано. Новый запуск не разрешён. /experiment')
        config = configuration()
        snapshot(bridge, session)
        current(bridge, session, event, config)
    document = event['terms']

    def consume(session, task):
        bridge.guard()
        actual, used = card(bridge, session, iid, intent)
        if used or actual != event or task.id != document['task_id']:
            raise Denied('experiment_approval_card_used_or_changed')
        snapshot(bridge, session)
        expires = current(bridge, session, actual, configuration(), state='READY', check_grants=False)
        bridge.store.audit(session, key(bridge, CONSUMED), 'owner', task.id, profile=bridge.profile, inbox_id=iid,
                           card=intent['card'], terms_hash=event['terms_hash'])
        bridge.finish(session, iid, 'Разрешение первого платного AI-теста сохранено. '
                      f'Лимит: {rub(document["budget"])}. Результат пока не получен. '
                      'Состояние: /experiment. Уведомления: /watch_experiment. Отмена: /cancel_experiment.')
        bridge.guard()
        if bridge.store.now(session) >= expires:
            raise Denied('experiment_approval_expired_during_commit')

    try:
        return Gateway.authorize_configured(bridge.store, config, 'owner', document['task_id'], document['version'],
            budget_nano_rub=document['budget'], seconds=document['seconds'], final_confirmation=True,
            expected_config_hash=document['profile_hash'], _scope_installer=consume)
    except Denied:
        # Another tap may have committed while this one waited for the F1 lock.
        # Only a recorded consumed card may become an idempotent acknowledgement.
        with bridge.store.transaction() as session:
            bridge.guard()
            bridge.store.check_audit(session)
            prior = session.get(TelegramInbox, iid)
            if (prior and prior.profile == bridge.profile and prior.state == 'DONE'
                    and prior.intent == intent and prior.fingerprint == digest(intent)):
                return
            _, used = card(bridge, session, iid, intent)
            if used:
                return bridge.finish(session, iid, 'Это разрешение уже использовано. Новый запуск не разрешён. /experiment')
        raise
