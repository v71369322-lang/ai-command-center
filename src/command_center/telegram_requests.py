"""Owner-only saved-request views; no planner, task creation or external calls."""

from sqlalchemy import or_, select

from .models import Audit, TelegramInbox
from .store import Denied, canonical, digest


def _captured_text(row, anchor, session=None):
    """Validate one checked intake, including accepted voice transcripts."""
    number = row.id.removeprefix(row.profile + ':')
    if (row.state != 'NEEDS_PLANNING' or not isinstance(row.intent, dict)
            or row.task_id is not None or row.fingerprint != digest(row.intent)
            or not isinstance(anchor, dict) or anchor.get('kind') != 'telegram_update_received'
            or anchor.get('actor') != 'owner' or anchor.get('profile') != row.profile
            or anchor.get('update_id') != number or anchor.get('intent_hash') != row.fingerprint):
        raise Denied('telegram_saved_request_integrity')
    if set(row.intent) == {'kind', 'text'} and row.intent.get('kind') == 'capture':
        value = row.intent.get('text')
    elif (session is not None and row.intent.get('kind') == 'voice_confirm'
          and row.intent.get('confirm') is True):
        accepted = session.execute(select(Audit).where(
            Audit.event['kind'].as_string() == 'telegram_voice_transcript_accepted',
            Audit.event['actor'].as_string() == 'owner',
            Audit.event['profile'].as_string() == row.profile,
            Audit.event['request_id'].as_string() == row.id,
            Audit.event['request_fingerprint'].as_string() == row.fingerprint)).scalar_one_or_none()
        value = accepted.event.get('text') if accepted else None
        if not accepted or accepted.event.get('text_hash') != digest(value):
            raise Denied('telegram_saved_request_integrity')
    else:
        raise Denied('telegram_saved_request_integrity')
    if not isinstance(value, str) or not 1 <= len(value.encode()) <= 2000:
        raise Denied('telegram_saved_request_integrity')
    return value


def captured_text(session, row):
    """Validate immutable intake before any reader copies its contents."""
    number = row.id.removeprefix(row.profile + ':')
    anchored = session.scalar(select(Audit).where(
                Audit.event['kind'].as_string() == 'telegram_update_received',
                Audit.event['actor'].as_string() == 'owner',
                Audit.event['profile'].as_string() == row.profile,
                Audit.event['update_id'].as_string() == number,
                Audit.event['intent_hash'].as_string() == row.fingerprint)
                .order_by(Audit.sequence).limit(1))
    return _captured_text(row, anchored.event if anchored else None, session)


def capture_receipt(inbox_id):
    number = inbox_id.rsplit(':', 1)[1]
    return (f'Запрос №{number} сохранён.\nПроверить: /request {number}\n'
            'Ожидает планирования. AI-планирование ещё не подключено; бизнес-действия не выполнялись.\n'
            'Выберите проект кнопкой ниже. Это только категория запроса.')


def project_queue(bridge, session, project='all'):
    """Profile-scoped, validated queue under the caller's existing audit lock."""
    from .project_inbox import IDS, PROJECTS, history
    if project not in IDS | {'all', 'unassigned'}:
        raise Denied('telegram_project_filter_invalid')
    assigned, _ = history(session)
    rows = session.execute(select(TelegramInbox).where(TelegramInbox.profile == bridge.profile,
        TelegramInbox.state == 'NEEDS_PLANNING', or_(
            TelegramInbox.intent['kind'].as_string() == 'capture',
            TelegramInbox.intent['kind'].as_string() == 'voice_confirm'))
        .order_by(TelegramInbox.created_at.desc(), TelegramInbox.id.desc()).limit(1001)).scalars().all()
    if len(rows) > 1000:
        raise Denied('telegram_inbox_capacity')
    counts = dict.fromkeys(['unassigned', *[key for key, _ in PROJECTS]], 0)
    selected = []
    for row in rows:
        value = captured_text(session, row)
        bridge.check_text(value)
        selection = assigned.get(row.id)
        if selection and selection['request_fingerprint'] != row.fingerprint:
            raise Denied('project_request_binding_changed')
        pid, version = (selection['project_id'], selection['version']) if selection else (None, 0)
        key = pid or 'unassigned'
        counts[key] += 1
        if (project == 'all' or project == key) and len(selected) < 5:
            selected.append((row, value, pid, version))
    return selected, counts


def projects_reply(bridge, session):
    from .project_inbox import PROJECTS
    from .project_connections import statuses
    _, counts = project_queue(bridge, session)
    connections = statuses(session)
    parts = [f'{label}: {counts[key]}\n/requests {key}\n/project {key} · '
             f'{"репозиторий проверен, запуск выключен" if key in connections else "не подключён"}'
             f'\n/connection {key}\n/setup {key}'
             for key, label in PROJECTS]
    parts.append(f'Не распределены: {counts["unassigned"]}\n/requests unassigned')
    return (f'Сохранённые запросы этого Telegram-подключения: {sum(counts.values())}.\n'
            'Ожидают планирования; выполнение не запускалось.\n\n' + '\n\n'.join(parts))


def project_reply(session, project_id):
    from .project_catalog import summary
    from .project_connections import statuses
    project = summary(project_id)
    connection = statuses(session).get(project_id)
    if not connection:
        state = ('Репозиторий не подключён. Следующий этап: ограничить GitHub App одним репозиторием, '
                 'проверить identity/default branch/baseline/branch protection и сохранить evidence.')
    else:
        state = (f"Репозиторий: {connection['repository']}\nBaseline: {connection['baseline_sha']}\n"
                 'Соединение проверено, но execution, paid AI, merge и deployment выключены.')
    return (f"{project['label']}\nРиск: {project['risk']}\nГраница: {project['boundary']}\n\n{state}\n\n"
            'Без отдельного плана и разрешения анализ, исправление и публикация не запускаются.')


def request_reply(bridge, session, intent, *, suffix=''):
    """Called under the existing admission/audit lock after audit validation."""
    query = select(TelegramInbox).where(TelegramInbox.profile == bridge.profile,
        TelegramInbox.state == 'NEEDS_PLANNING', or_(
            TelegramInbox.intent['kind'].as_string() == 'capture',
            TelegramInbox.intent['kind'].as_string() == 'voice_confirm'))
    if intent['kind'] == 'request':
        query = query.where(TelegramInbox.id == bridge.profile + ':' + intent['number'])
    from .project_inbox import history, PROJECTS
    if intent['kind'] == 'requests':
        project = intent.get('project', 'all')
        selected, counts = project_queue(bridge, session, project)
        if project != 'all':
            label = dict(PROJECTS).get(project, 'Не распределены')
            header = f'Очередь: {label}. Ожидают планирования: {counts[project]}.\n\n'
            if not selected:
                return header + 'Сохранённых запросов этого проекта в этом Telegram-подключении пока нет.'
            header += 'Последние запросы (до 5):\n\n'
        else:
            header = 'Последние сохранённые запросы (до 5):\n\n'
    else:
        rows = session.execute(query.limit(1)).scalars().all()
        assigned, _ = history(session)
        selected = []
        for row in rows:
            value = captured_text(session, row)
            bridge.check_text(value)
            selection = assigned.get(row.id)
            if selection and selection['request_fingerprint'] != row.fingerprint:
                raise Denied('project_request_binding_changed')
            pid, version = (selection['project_id'], selection['version']) if selection else (None, 0)
            selected.append((row, value, pid, version))
        header = ''
    if not selected:
        return ('Сохранённых запросов в этом Telegram-подключении пока нет.' if intent['kind'] == 'requests'
                else 'Запрос не найден среди сохранённых запросов этого Telegram-подключения.')
    # Transport limits apply to escaped JSON bytes as well as text characters.
    # Shrink previews only; keep request numbers, labels and safety notices.
    widths = range(160, -1, -16) if intent['kind'] == 'requests' else (None,)
    for width in widths:
        parts = []
        for row, value, pid, version in selected:
            number = row.id.removeprefix(bridge.profile + ':')
            project_label = dict(PROJECTS).get(pid, 'Не распределён')
            if width is not None:
                preview = ' '.join(value.split())
                value = preview[:width] + ('…' if len(preview) > width else '')
            parts.append(f'Запрос №{number}\nТекст запроса (не команда):\n{value}\n'
                         f'Проект: {project_label}. Версия назначения: {version}.\n'
                         f'Ожидает планирования. Выполнение не запускалось.\nОткрыть: /request {number}')
        reply = header + '\n\n'.join(parts)
        full = reply + suffix
        if len(full) <= 4096 and len(canonical({'chat_id': bridge.owner, 'text': full}).encode()) <= 8192:
            return reply
    raise Denied('telegram_saved_reply_size')
