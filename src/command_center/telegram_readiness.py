"""Read-only owner summary; local configuration is never remote API evidence."""
import os
import re

from sqlalchemy import func, select

from .coding.integration_config import IntegrationConfig
from .models import Control, Task, TelegramInbox


GATES = {
    'model_access': 'доступность модели для аккаунта',
    'current_price': 'актуальный тариф',
    'payment_bound': 'верхняя граница расходов с курсом и комиссиями',
    'openai_credential': 'защищённый OpenAI credential',
    'github_app': 'минимальные права GitHub App',
    'repository': 'отдельный синтетический репозиторий',
    'runtime': 'готовность исполнителя',
    'dry_run': 'успешный dry-run',
    'existing_funding': 'доступный API-баланс',
}


def reply(bridge, session):
    store = bridge.store
    control = session.get(Control, 1)
    now = store.now(session)
    state = ('восстановление; новые запуски заблокированы' if control.recovery else
             'обычная остановка; новые запуски заблокированы' if control.halted else
             'приём разрешённых задач открыт; каждой задаче нужны свои полномочия')
    pending = session.scalar(select(func.count()).select_from(TelegramInbox).where(
        TelegramInbox.profile == bridge.profile, TelegramInbox.state == 'NEEDS_PLANNING'))
    unresolved = session.scalar(select(func.count()).select_from(Task).where(
        Task.state.in_(['RUNNING', 'VERIFYING', 'CANCEL_REQUESTED', 'RECONCILING', 'SECURITY_BLOCKED'])))
    revision = store.settings.source_revision
    revision = revision if re.fullmatch('[a-f0-9]{40}', revision) else 'не подтверждена'
    lines = ['Состояние AI Commander', f'Снимок UTC: {now.isoformat()}', f'Версия обработчика: {revision}',
             f'Управление: {state}.', f'Исполнения, требующие сверки перед resume: {unresolved}.',
             f'Запросы этого Telegram-подключения, ожидающие планирования: {pending}.',
             'AI-планирование этих запросов пока не подключено. /coding_plan — только mock-упражнение.']
    # Only the opt-in deployment shares the pinned config, never credential files.
    # Absence here must NOT be advertised as global live-disabled.
    if not os.environ.get('F2_INTEGRATION_CONFIG_FILE'):
        lines += ['AI-профиль не предоставлен этому обработчику. Состояние gateway неизвестно.']
    else:
        try:
            config = IntegrationConfig.load()
            report = config.first_experiment.report(now) if config.first_experiment else None
        except (ValueError, OSError):
            # Never expose a parsing exception: it may contain paths or values.
            lines += ['Локальный AI-профиль не удалось проверить. Состояние gateway неизвестно.']
        else:
            mode = {'disabled': 'выключен', 'http_mock': 'HTTP-моки',
                    'live': 'live; наличие конфигурации не подтверждает работоспособность'}[config.mode]
            lines += [f'Режим локального AI-профиля: {mode}.']
            if config.mode == 'live':
                lines += ['Операторский live-флаг: ' + ('включён' if config.live_authorized else 'выключен')
                          + '; он не заменяет отдельное разрешение задачи.']
            if report is None:
                lines += ['Профиль первого AI-эксперимента не задан.']
            else:
                missing = [GATES[key] for key, current in report['gates'].items() if not current]
                lines += [('Восстановительный тест: один AI-вызов, без исправлений и повторов; '
                           'исходная задача и расход сохраняются.' if config.first_experiment.call_limit == 1 else
                           'Первый эксперимент: не более 100 ₽ суммарно, до 2 вызовов и 1 исправления.'),
                          'Не подтверждено или просрочено: ' + '; '.join(missing) + '.' if missing else
                          'Все предварительные свидетельства актуальны в локальном профиле; '
                          'это ещё не окончательное разрешение запуска.']
    lines += ['OpenAI, GitHub, ключи, фактические списания и здоровье worker/watchdog этой командой не проверяются.',
              'Синтетический бюджет не является балансом OpenAI. Сводка сохраняет расходы и спорные резервы без изменений.',
              'Сводка не запускает задачи, не снимает остановку и не выдаёт разрешение на расходы. '
              'Для нового снимка повторите /readiness.']
    return '\n\n'.join(lines)
