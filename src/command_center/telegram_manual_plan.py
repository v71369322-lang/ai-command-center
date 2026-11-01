"""Version-fenced owner-authored plan commands; no JSON/provider/tool instructions."""
from uuid import NAMESPACE_URL, uuid5

from .manual_plan import references, save
from .request_plan_store import ManualContent, ManualRequest
from .store import Denied, canonical
from .telegram_project_setup import _bound


def number(value, maximum):
    import re
    if not re.fullmatch(r'0|[1-9][0-9]{0,15}', value) or int(value) > maximum:
        raise Denied('telegram_manual_plan_reference_invalid')
    return int(value)


def parse(text):
    lines = text.splitlines()
    head = lines[0].split()
    if len(head) != 5:
        raise Denied('telegram_manual_plan_arguments_invalid')
    n, assignment, setup, plan = [number(v, cap) for v, cap in zip(head[1:], [2**53-1, 1000, 500, 100])]
    summary, steps, questions = None, [], []
    for line in lines[1:]:
        if not line.strip() or line.startswith('# '):
            continue
        kind, separator, value = line.partition(':')
        value = value.strip()
        if not separator or not value:
            raise Denied('telegram_manual_plan_text_invalid')
        if kind == 'Кратко' and summary is None and not steps and not questions:
            summary = value
        elif kind == 'Шаг' and summary is not None and not questions:
            steps.append({'description': value, 'acceptance': []})
        elif kind == 'Готово' and steps and not questions:
            steps[-1]['acceptance'].append(value)
        elif kind == 'Вопрос' and steps:
            questions.append(value)
        else:
            raise Denied('telegram_manual_plan_text_invalid')
    try:
        draft = ManualContent(summary=summary, steps=steps, questions=questions)
    except ValueError:
        raise Denied('telegram_manual_plan_text_invalid') from None
    if draft.summary == '[опишите цель]' or any(s.description == '[опишите шаг]' or '[проверяемый результат]' in s.acceptance for s in draft.steps):
        raise Denied('telegram_manual_plan_replace_template')
    if assignment < 1:
        raise Denied('telegram_manual_plan_project_required')
    return {'kind': 'manual_plan_save', 'number': str(n), 'assignment': assignment, 'setup': setup,
            'plan': plan, 'draft': draft.model_dump()}


def template(bridge, session, intent, suffix):
    from .models import TelegramInbox
    rid = bridge.profile + ':' + intent['number']
    if session.get(TelegramInbox, rid) is None:
        return 'Запрос не найден среди сохранённых запросов этого Telegram-подключения.'
    try:
        _, _, _, ref = references(bridge.store, session, rid)
    except Denied as error:
        if str(error) != 'manual_plan_project_required':
            raise
        return f'Сначала выберите проект: /request {intent["number"]}. Ручной план ещё не создан.'
    text = (f'/draft_plan {intent["number"]} {ref["expected_assignment_version"]} {ref["expected_setup_version"]} {ref["expected_plan_version"]}\n'
            'Кратко: [опишите цель]\nШаг: [опишите шаг]\nГотово: [проверяемый результат]\n'
            '# Скопируйте сообщение, замените текст в скобках и отправьте. Строки с # — подсказки, не часть плана.\n'
            '# Можно добавить до 8 шагов с 1–3 критериями «Готово» и до 5 строк «Вопрос». Большие планы правьте в мобильной панели.\n'
            '# Числа защищают от смены проекта, настроек и версии плана. Новый шаблон: /plan_edit '+intent['number']+'.\n'
            '# Сохранится только черновик владельца — без AI, запуска, расходов и прав на проекты. Ключи, пароли и клиентские данные не вводите.')
    if len(text+suffix)>4096 or len(canonical({'chat_id':bridge.owner,'text':text+suffix}).encode())>8192:
        raise Denied('telegram_manual_plan_reply_size')
    return text


def apply(bridge, iid, intent):
    with bridge.store.transaction() as session:
        bridge.store.check_audit(session)
        if _bound(bridge, session, iid, intent).state == 'DONE':
            return
        context, setup, _, ref = references(bridge.store, session, bridge.profile + ':' + intent['number'])
        if (context.assignment_version != intent['assignment'] or setup['version'] != intent['setup']
                or ref['expected_plan_version'] != intent['plan']):
            bridge.finish(session, iid, f'План не сохранён: сведения изменились. Получите новый шаблон: /plan_edit {intent["number"]}.')
            return
        request = ManualRequest(**ref, draft=ManualContent.model_validate(intent['draft']))
    def finish(session, result):
        if _bound(bridge, session, iid, intent).state != 'DONE':
            bridge.finish(session, iid, f'Ручной план запроса №{intent["number"]} сохранён: версия {result["version"]}. '
                f'Автор — владелец. Просмотр: /plan {intent["number"]}. Обзор: /review {intent["number"]}. '
                'AI не вызывался; задача, расходы и доступы не разрешены.')
    try:
        save(bridge.store, 'owner', request, str(uuid5(NAMESPACE_URL,'acc:telegram-manual-plan:'+iid)), _scope_installer=finish)
    except Denied as error:
        if str(error) != 'manual_plan_context_changed':
            raise
        with bridge.store.transaction() as session:
            bridge.store.check_audit(session)
            if _bound(bridge, session, iid, intent).state != 'DONE':
                bridge.finish(session, iid, f'План не сохранён: сведения изменились. Получите новый шаблон: /plan_edit {intent["number"]}.')
