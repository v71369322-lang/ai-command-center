"""Truthful owner-facing architecture/status view without external probes."""

from sqlalchemy import func, select

from .models import Control, TelegramInbox
from .store import Denied
from .telegram_voice_requests import pending_count


def reply(session, profile):
    control = session.get(Control, 1)
    if control is None:
        raise Denied('control_missing')
    text_pending = session.scalar(select(func.count()).select_from(TelegramInbox).where(
        TelegramInbox.profile == profile, TelegramInbox.state == 'NEEDS_PLANNING'))
    if type(text_pending) is not int or not 0 <= text_pending <= 1000:
        raise Denied('telegram_system_counts_invalid')
    admission = 'остановлен' if control.halted or control.recovery else 'открыт'
    return (f'Контур AI Commander (локальная сводка)\n\n'
            f'• Telegram и диспетчер: команда принята; вход новых запусков {admission}.\n'
            f'• Очередь: текстовых запросов {text_pending}; голосовых до расшифровки {pending_count(session, profile)}.\n'
            '• AI-аналитик: контракт и строгая проверка ответа готовы; доступ провайдера этой командой не проверяется.\n'
            '• Исполнитель: изолированный coding-контур проверен на синтетическом упражнении; '
            'обычные проекты ещё не подключены.\n'
            '• Проверяющий: проверяет результат, source revision и границы полномочий; '
            'отклонённый ответ не публикуется.\n'
            '• Watchdog: контролирует зависшие исполнения; его здоровье на VPS этой командой не проверяется.\n'
            '• Автоисправление проектов: пока не включено. Для каждого проекта потребуются отдельный '
            'репозиторий, ограниченный доступ, тесты и PR.\n\n'
            'Сводка ничего не запускает, не обращается к внешним API и не изменяет проекты.')
