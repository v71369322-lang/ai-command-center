"""Paginated private-owner draft readback. No generation, grant or task execution."""
from .models import TelegramInbox
from .project_inbox import PROJECTS
from .request_plan_store import read_locked
from .store import Denied, canonical

MAX_PAGES = 50


def reply(bridge, session, intent, suffix):
    number, page = intent['number'], intent['page']
    rid = bridge.profile + ':' + number
    if session.get(TelegramInbox, rid) is None:
        return 'Запрос не найден среди сохранённых запросов этого Telegram-подключения.'
    result = read_locked(bridge.store, session, rid, version=intent['version'])
    if result['state'] == 'MISSING_VERSION':
        return f'Указанный черновик не найден. Открыть последний: /plan {number}'
    if result['state'] == 'MISSING':
        return (f'Черновик плана для запроса №{number} пока не сохранён. '
                'AI-планирование обычных запросов ещё не подключено. Просмотр не запускает генерацию. '
                f'Ручной план: /plan_edit {number}. Запрос: /request {number}')
    if result['state'] == 'STALE':
        return (f'Сохранённый черновик для запроса №{number} устарел: запрос, проект или условия изменились. '
                'Новый план автоматически не создавался. '
                f'Ручной план: /plan_edit {number}. Запрос: /request {number}')
    plan = result['proposal']
    lines = [f'Кратко: {plan["summary"]}', 'Статус: ' + (
        'нужны уточнения.' if plan['disposition'] == 'needs_clarification' else 'можно рассмотреть предложение.')]
    for index, step in enumerate(plan['steps'], 1):
        lines.append(f'{index}. {step["description"]}')
        lines.extend('  • Критерий готовности: ' + value for value in step['acceptance'])
    if plan['questions']:
        lines.append('Уточнения:')
        lines.extend('? ' + value for value in plan['questions'])
    for value in [plan['summary'], *plan['questions'],
                  *[v for step in plan['steps'] for v in [step['description'], *step['acceptance']]]]:
        bridge.check_text(value)  # Includes the current transport's credential screen.
    project = dict(PROJECTS).get(result['project_id'], 'Не распределён')

    def body(content, index, total, following=True):
        origin = ('Автор: владелец. Это ручной черновик, не разрешение на действия.\n'
                  if result.get('origin') == 'owner_authored' else
                  'Источник AI-ответа не подтверждён. Это предложение, не разрешение на действия.\n')
        text = (f'План запроса №{number}. Черновик {result["version"]}.\nПроект: {project}.\n'
                + origin +
                f'Страница {index}/{total}.\n\n' + '\n'.join(content))
        if following:
            text += f'\n\nДалее: /plan {number} {result["version"]} {index + 1}'
        return text

    def fits(text):
        return len(text + suffix) <= 4096 and len(canonical({'chat_id': bridge.owner, 'text': text + suffix}).encode()) <= 8192

    pages, current = [], []
    for line in lines:
        if not fits(body([*current, line], MAX_PAGES, MAX_PAGES)):
            if not current or not fits(body([line], MAX_PAGES, MAX_PAGES)):
                raise Denied('planning_draft_reply_size')
            pages.append(current)
            current = []
        current.append(line)
    if current:
        pages.append(current)
    if len(pages) > MAX_PAGES:
        raise Denied('planning_draft_reply_size')
    if page > len(pages):
        return f'У черновика {len(pages)} стр. Открыть: /plan {number} {result["version"]} 1'
    text = body(pages[page - 1], page, len(pages), following=page < len(pages))
    if not fits(text):
        raise Denied('planning_draft_reply_size')
    return text
