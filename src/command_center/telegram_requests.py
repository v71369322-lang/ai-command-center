"""Owner-only saved-request views; no planner, task creation or external calls."""

from sqlalchemy import select

from .models import Audit, TelegramInbox
from .store import Denied, digest


def captured_text(session, row):
    """Validate immutable intake before any reader copies its contents."""
    number = row.id.removeprefix(row.profile + ':')
    if (row.state != 'NEEDS_PLANNING' or not isinstance(row.intent, dict)
            or set(row.intent) != {'kind', 'text'} or row.intent.get('kind') != 'capture'
            or row.task_id is not None or row.fingerprint != digest(row.intent)
            or not isinstance(row.intent.get('text'), str) or not 1 <= len(row.intent['text'].encode()) <= 2000
            or not session.execute(select(Audit).where(
                Audit.event['kind'].as_string() == 'telegram_update_received',
                Audit.event['actor'].as_string() == 'owner',
                Audit.event['profile'].as_string() == row.profile,
                Audit.event['update_id'].as_string() == number,
                Audit.event['intent_hash'].as_string() == row.fingerprint)).first()):
        raise Denied('telegram_saved_request_integrity')
    return row.intent['text']


def capture_receipt(inbox_id):
    number = inbox_id.rsplit(':', 1)[1]
    return (f'Запрос №{number} сохранён.\nПроверить: /request {number}\n'
            'Ожидает планирования. AI-планирование ещё не подключено; бизнес-действия не выполнялись.')


def request_reply(bridge, session, intent):
    """Called under the existing admission/audit lock after audit validation."""
    query = select(TelegramInbox).where(TelegramInbox.profile == bridge.profile,
        TelegramInbox.state == 'NEEDS_PLANNING', TelegramInbox.intent['kind'].as_string() == 'capture')
    if intent['kind'] == 'request':
        query = query.where(TelegramInbox.id == bridge.profile + ':' + intent['number'])
    rows = session.execute(query.order_by(TelegramInbox.created_at.desc(), TelegramInbox.id.desc()).limit(5)).scalars().all()
    if not rows:
        return ('Сохранённых запросов в этом Telegram-подключении пока нет.' if intent['kind'] == 'requests'
                else 'Запрос не найден среди сохранённых запросов этого Telegram-подключения.')
    from .project_inbox import history, PROJECTS
    assigned, _ = history(session)
    parts = []
    for row in rows:
        number = row.id.removeprefix(bridge.profile + ':')
        value = captured_text(session, row)
        bridge.check_text(value)
        selection = assigned.get(row.id)
        if selection and selection['request_fingerprint'] != row.fingerprint:
            raise Denied('project_request_binding_changed')
        pid, version = (selection['project_id'], selection['version']) if selection else (None, 0)
        project_label = dict(PROJECTS).get(pid, 'Не распределён')
        if intent['kind'] == 'requests':
            preview = ' '.join(value.split())
            value = preview[:160] + ('…' if len(preview) > 160 else '')
        parts.append(f'Запрос №{number}\nТекст запроса (не команда):\n{value}\n'
                     f'Проект: {project_label}. Версия назначения: {version}.\n'
                     f'Ожидает планирования. Выполнение не запускалось.\nОткрыть: /request {number}')
    return ('Последние сохранённые запросы (до 5):\n\n' if intent['kind'] == 'requests' else '') + '\n\n'.join(parts)
