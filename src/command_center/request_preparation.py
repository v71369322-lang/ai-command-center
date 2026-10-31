"""A checked preparation queue. Stages describe drafts, never execution authority."""
import re

from sqlalchemy import select, tuple_

from .models import Audit, Control, TelegramInbox
from .project_inbox import IDS, PROJECTS, check_content, history, owner
from .project_setup import _view, records as setup_records
from .request_plan_store import _read_context, _records
from .request_planning import _context_values
from .request_review import preparation_step
from .store import Denied, canonical, digest
from .telegram_requests import _captured_text

STAGES = {
    'select_project': 'Выбрать проект', 'complete_setup': 'Заполнить настройки',
    'prepare_plan': 'Составить план', 'refresh_plan': 'Обновить устаревший план',
    'answer_questions': 'Уточнить вопросы', 'verify_scope': 'Сверить задачу и подключения',
}
PAGE_SIZE = 10
MAX_REQUESTS = 1000


def read_locked(store, session, *, project='all', stage='all', page=1, snapshot=None, profile=None, page_size=PAGE_SIZE):
    """Caller owns checked Control transaction; batch inputs are loaded once."""
    if (not isinstance(project, str) or project not in IDS | {'all', 'unassigned'}
            or not isinstance(stage, str) or stage not in {'all', *STAGES}
            or type(page) is not int or not 1 <= page <= 200 or type(page_size) is not int or page_size not in {5, PAGE_SIZE}
            or snapshot is not None and (not isinstance(snapshot, str) or not re.fullmatch(r'[a-f0-9]{64}', snapshot))
            or profile is not None and (not isinstance(profile, str) or not re.fullmatch(r'[a-f0-9]{64}', profile))):
        raise Denied('preparation_queue_arguments_invalid')
    query = select(TelegramInbox).where(TelegramInbox.state == 'NEEDS_PLANNING')
    if profile is not None:
        query = query.where(TelegramInbox.profile == profile)
    rows = session.scalars(query.order_by(TelegramInbox.created_at.desc(), TelegramInbox.id.desc())
                           .limit(MAX_REQUESTS + 1)).all()
    if len(rows) > MAX_REQUESTS:
        raise Denied('preparation_queue_capacity')
    # The same earliest owner receive anchor as the individual context reader.
    fields = [Audit.event[key].as_string() for key in ('profile', 'update_id', 'intent_hash')]
    anchors = {}
    if rows:
        keys = [(r.profile, r.id.removeprefix(r.profile + ':'), r.fingerprint) for r in rows]
        events = session.scalars(select(Audit).where(Audit.event['kind'].as_string() == 'telegram_update_received',
            Audit.event['actor'].as_string() == 'owner', tuple_(*fields).in_(keys))
            .distinct(*fields).order_by(*fields, Audit.sequence).limit(MAX_REQUESTS)).all()
        anchors = {(a.event['profile'], a.event['update_id'], a.event['intent_hash']): a.event for a in events}
    assigned, _ = history(session)
    latest, _, setup_snapshots = setup_records(store, session)
    plans = _records(session)
    setups = {}
    def setup_reader(pid, selected=None):
        key = (pid, selected)
        if key not in setups:
            setups[key] = _view(pid, latest, setup_snapshots, selected)
        return setups[key]
    control = session.get(Control, 1)
    projects = dict.fromkeys(['unassigned', *[key for key, _ in PROJECTS]], 0)
    stages = dict.fromkeys(STAGES, 0)
    prepared, bindings = [], []
    for row in rows:
        anchor = anchors.get((row.profile, row.id.removeprefix(row.profile + ':'), row.fingerprint))
        value = _captured_text(row, anchor)
        check_content(store, value)
        context = _context_values(store, row, value, assigned.get(row.id), anchor, control)
        plan = _read_context(store, context, plans, setup_reader)
        setup = setup_reader(context.project_id) if context.project_id else None
        setup_state = ('UNASSIGNED' if setup is None else 'EMPTY' if setup['version'] == 0 else
                       'COMPLETE' if setup['review']['ready_for_operator_review'] else 'INCOMPLETE')
        plan_state = 'NEEDS_CLARIFICATION' if plan['proposal'] and plan['proposal']['questions'] else plan['state']
        step = preparation_step(context.project_id is not None, setup_state, plan_state)
        item = {'id': row.id, 'text': value, 'project_id': context.project_id,
                'assignment_version': context.assignment_version, 'setup_version': setup['version'] if setup else None,
                'plan_version': plan['latest_version'], 'plan_state': plan_state, 'setup_state': setup_state,
                'origin': plan.get('origin'), 'stage': step}
        bindings.append({'row': item, 'context': context.binding, 'setup': setup['draft_digest'] if setup else None})
        key = context.project_id or 'unassigned'
        projects[key] += 1
        if project == 'all' or project == key:
            stages[step] += 1
            if stage == 'all' or stage == step:
                prepared.append(item)
    binding = digest({'schema': 1, 'project': project, 'stage': stage, 'profile': profile, 'page_size': page_size,
                      'source': store.settings.source_revision, 'epoch': control.epoch,
                      'halted': control.halted, 'recovery': control.recovery, 'rows': bindings})
    if snapshot is not None and snapshot != binding:
        raise Denied('preparation_queue_changed')
    pages = max(1, (len(prepared) + page_size - 1) // page_size)
    if page > pages:
        raise Denied('preparation_queue_page_missing')
    result = {'schema': 1, 'scope': 'PREPARATION_QUEUE_ONLY', 'project': project, 'stage': stage,
              'page': page, 'page_size': page_size, 'pages': pages, 'total_pending': len(rows),
              'total_matching': len(prepared), 'project_counts': projects, 'stage_counts': stages,
              'requests': prepared[(page-1)*page_size:page*page_size],
              'snapshot_digest': binding, 'observed_at': store.now(session).isoformat(),
              'execution_ready': False, 'execution_authorized': False, 'external_checks_performed': False,
              'provider_called': False, 'task_created': False, 'actions_enabled': []}
    if len(canonical(result).encode()) > 65536:
        raise Denied('preparation_queue_size')
    return result


def read(store, role, **kwargs):
    owner(role)
    with store.transaction() as session:
        store.check_audit(session)
        return read_locked(store, session, **kwargs)


def telegram_parse(text):
    parts = text.split()
    if (len(parts) not in {1, 2, 3, 4}
            or len(parts) >= 2 and parts[1] not in IDS | {'all', 'unassigned'}
            or len(parts) >= 3 and parts[2] not in {'all', *STAGES}
            or len(parts) == 4 and (not re.fullmatch(r'[1-9][0-9]{0,2}', parts[3]) or int(parts[3]) > 200)):
        raise Denied('telegram_preparation_queue_arguments_invalid')
    return {'kind': 'preparation_queue', 'project': parts[1] if len(parts) >= 2 else 'all',
            'stage': parts[2] if len(parts) >= 3 else 'all', 'page': int(parts[3]) if len(parts) == 4 else 1}


def telegram_reply(bridge, session, intent, suffix):
    try:
        result = read_locked(bridge.store, session, project=intent['project'], stage=intent['stage'],
                             page=intent['page'], profile=bridge.profile, page_size=5)
    except Denied as error:
        if str(error) != 'preparation_queue_page_missing':
            raise
        return 'Страницы уже нет. Откройте новый обзор: /queue. Просмотр не запускает задачи.'
    for width in (100, 50, 0):
        lines = [f'Подготовка запросов. Снимок UTC: {result["observed_at"]}',
                 f'Найдено: {result["total_matching"]} из {result["total_pending"]}. Страница {result["page"]}/{result["pages"]}.',
                 f'Проект: {dict(PROJECTS).get(intent["project"], "Все проекты" if intent["project"] == "all" else "Не распределены")}. Стадия: {STAGES.get(intent["stage"], "все")}.',
                 'Стадии выбранного проекта:']
        lines += [f'{label}: {result["stage_counts"][key]} · /queue {intent["project"]} {key}' for key, label in STAGES.items()]
        for row in result['requests']:
            preview = ' '.join(row['text'].split())
            preview = preview[:width] + ('…' if len(preview) > width else '')
            bridge.check_text(row['text'])
            number = row['id'].rsplit(':', 1)[1]
            lines += [f'\nЗапрос №{number} · {dict(PROJECTS).get(row["project_id"], "Не распределён")}',
                      STAGES[row['stage']], f'Текст (кратко): {preview}', f'Открыть: /review {number}']
        if not result['requests']:
            lines.append('В этом разделе запросов пока нет.')
        for label, page in [('Назад', result['page']-1), ('Далее', result['page']+1)]:
            if 1 <= page <= result['pages']:
                lines.append(f'{label}: /queue {intent["project"]} {intent["stage"]} {page}')
        lines += ['Фильтр: /queue project-id stage. Например: /queue all answer_questions.',
                  'Каждая новая команда читает новый снимок; позиции могут измениться.',
                  'Это стадии подготовки, не разрешение запуска. AI и внешние подключения не проверялись.']
        text = '\n'.join(lines)
        # Input snippets use the 2000-byte guard above; composed replies use Bot API limits.
        check_content(bridge.store, text)
        from .telegram_transport import ConfiguredTelegramHTTP
        if isinstance(bridge.client, ConfiguredTelegramHTTP) and bridge.client.sensitive(text):
            raise Denied('telegram_secret_content_forbidden')
        if len(text+suffix) <= 4096 and len(canonical({'chat_id': bridge.owner, 'text': text+suffix}).encode()) <= 8192:
            return text
    raise Denied('preparation_queue_reply_size')
