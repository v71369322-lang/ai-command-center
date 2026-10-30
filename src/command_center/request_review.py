"""One checked, owner-only request/project/plan snapshot. Never dispatches work."""
from .project_connections import REPOSITORIES
from .project_inbox import PROJECTS, owner
from .project_setup import read_locked as setup_read
from .request_plan_store import read_locked as plan_read
from .request_planning import _context
from .store import Denied, canonical, digest

NEXT = {
    'select_project': 'Выберите проект для запроса.',
    'complete_setup': 'Заполните черновик подключения выбранного проекта.',
    'prepare_plan': 'План запроса ещё не сохранён. AI-планирование обычных запросов пока не подключено.',
    'refresh_plan': 'Сохранённый план устарел. Требуется новый план для текущих условий.',
    'answer_questions': 'В предложении есть вопросы. Уточните требования перед дальнейшей подготовкой.',
    'verify_scope': 'Сверьте предложение с настройками проекта, затем проверьте доступы и среду выполнения.',
}
CHECKS = (
    ('assignment', 'Выбор проекта'), ('setup', 'Настройки проекта'), ('plan', 'Предложение плана'),
    ('plan_setup_binding', 'Соответствие плана настройкам'), ('repository', 'Доступ к репозиторию'),
    ('verification', 'Изолированная проверка'), ('delivery', 'Доставка на сервер'),
    ('authorization', 'Разрешение задачи и расходов'), ('admission', 'Приём новых запусков'),
)


def read_locked(store, session, request_id):
    """Caller owns the existing checked F1 Control transaction."""
    context = _context(store, session, request_id)
    plan = plan_read(store, session, request_id)
    if plan['state'] not in {'CURRENT', 'STALE', 'MISSING'}:
        raise Denied('request_review_plan_state_invalid')
    project = None
    setup_state = 'UNASSIGNED'
    if context.project_id is not None:
        setup = setup_read(store, session, context.project_id)
        project = {'id': context.project_id, 'label': dict(PROJECTS)[context.project_id],
                   'repository': REPOSITORIES[context.project_id], 'setup_version': setup['version'],
                   'setup_digest': setup['draft_digest'], 'draft': setup['draft'], 'review': setup['review']}
        setup_state = 'EMPTY' if setup['version'] == 0 else (
            'COMPLETE' if setup['review']['ready_for_operator_review'] else 'INCOMPLETE')
    proposal = plan['proposal']
    plan_state = 'NEEDS_CLARIFICATION' if proposal and proposal['questions'] else plan['state']
    states = {'assignment': 'SELECTED' if project else 'UNASSIGNED', 'setup': setup_state, 'plan': plan_state,
              'plan_setup_binding': 'NOT_CHECKED', 'repository': 'NOT_CHECKED', 'verification': 'NOT_CHECKED',
              'delivery': 'NOT_CHECKED', 'authorization': 'NOT_GRANTED',
              'admission': 'RECOVERY' if context.recovery else 'HALTED' if context.halted else 'OPEN'}
    next_step = ('select_project' if not project else 'complete_setup' if setup_state != 'COMPLETE'
                 else 'prepare_plan' if plan_state == 'MISSING' else 'refresh_plan' if plan_state == 'STALE'
                 else 'answer_questions' if plan_state == 'NEEDS_CLARIFICATION' else 'verify_scope')
    result = {'schema': 1, 'scope': 'REQUEST_REVIEW_ONLY',
              'source_revision': context.source_revision, 'context_digest': context.binding,
              'request': {'id': context.request_id, 'text': context.text,
                          'fingerprint': context.request_fingerprint, 'assignment_version': context.assignment_version},
              'project': project,
              'plan': {'state': plan_state, 'version': plan['version'], 'latest_version': plan['latest_version'],
                       'proposal': proposal, 'provider_evidence_verified': False, 'setup_binding_verified': False},
              'checks': [{'id': key, 'label': label, 'state': states[key]} for key, label in CHECKS],
              'blocking_checks': [key for key, _ in CHECKS if states[key] not in {'SELECTED', 'COMPLETE', 'CURRENT', 'OPEN'}],
              'next_step': next_step, 'execution_ready': False, 'execution_authorized': False,
              'external_checks_performed': False, 'task_created': False, 'provider_called': False, 'actions_enabled': []}
    result.update(snapshot_digest=digest(result), observed_at=store.now(session).isoformat())
    if len(canonical(result).encode()) > 65536:
        raise Denied('request_review_size')
    return result


def read(store, role, request_id):
    owner(role)
    with store.transaction() as session:
        store.check_audit(session)
        return read_locked(store, session, request_id)


def telegram_reply(bridge, session, intent, suffix):
    """Profile-scoped short review; existing readers retain the full documents."""
    from .models import TelegramInbox
    rid = bridge.profile + ':' + intent['number']
    if session.get(TelegramInbox, rid) is None:
        return 'Запрос не найден среди сохранённых запросов этого Telegram-подключения.'
    view = read_locked(bridge.store, session, rid)
    project, plan = view['project'], view['plan']
    setup_states = {'UNASSIGNED': 'проект не выбран', 'EMPTY': 'черновик пуст',
                    'INCOMPLETE': 'черновик неполный', 'COMPLETE': 'черновик заполнен, внешние проверки обязательны'}
    plan_states = {'MISSING': 'не сохранён', 'STALE': 'устарел', 'CURRENT': 'непроверенное предложение',
                   'NEEDS_CLARIFICATION': 'нужны уточнения'}
    state = {r['id']: r['state'] for r in view['checks']}
    admission = {'OPEN': 'обычная остановка не включена; отдельные разрешения всё равно нужны',
                 'HALTED': 'новые запуски остановлены', 'RECOVERY': 'нужна сверка восстановления'}
    for width in (120, 60, 0):
        preview = ' '.join(view['request']['text'].split())
        preview = preview[:width] + ('…' if len(preview) > width else '')
        text = (f'Подготовка запроса №{intent["number"]}\nСнимок UTC: {view["observed_at"]}\n'
                f'Текст (кратко, не команда): {preview}\n'
                f'Проект: {project["label"] if project else "не выбран"}. '
                f'Версия назначения: {view["request"]["assignment_version"]}.\n'
                f'Настройки: {setup_states[state["setup"]]}.\n'
                f'План: {plan_states[plan["state"]]}. Версия: {plan["version"] or 0}.\n'
                'Соответствие плана настройкам, доступ к репозиторию, изолированная проверка и доставка не проверены.\n'
                'Разрешение на выполнение и расходы не выдано.\n'
                f'Приём запусков: {admission[state["admission"]]}.\n\nДальше: {NEXT[view["next_step"]]}\n'
                f'Полный запрос: /request {intent["number"]}. План: /plan {intent["number"]}.')
        if project:
            text += f' Настройки: /setup {project["id"]} (версия {project["setup_version"]}).'
        text += '\nЭто текущий обзор сохранённых данных; просмотр не создаёт задачу и не обращается к AI.'
        bridge.check_text(text)
        if len(text + suffix) <= 4096 and len(canonical({'chat_id': bridge.owner, 'text': text + suffix}).encode()) <= 8192:
            return text
    raise Denied('request_review_reply_size')
