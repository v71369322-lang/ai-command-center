"""Owner-visible, expiring polling evidence; never a credential or task authority."""
from datetime import datetime
import json
import re

from sqlalchemy import select

from .models import Audit
from .store import Denied, digest


def scope(value):
    try:
        data = json.loads(value)
        if (set(data) != {'mode', 'owner_id', 'bot_id', 'connection_digest'}
                or data['mode'] not in {'live', 'http_mock'}
                or any(type(data[k]) is not int or not 0 < data[k] < 2**52 for k in ('owner_id', 'bot_id'))
                or not isinstance(data['connection_digest'], str)
                or not re.fullmatch('[a-f0-9]{64}', data['connection_digest'])):
            raise ValueError('invalid_scope')
        return data
    except (ValueError, TypeError, KeyError):
        raise Denied('telegram_status_binding_invalid') from None


def status(store, binding):
    result = {'mode': 'disabled', 'status': 'disabled', 'live_connected': False,
              'voice_enabled': False, 'description': 'Бот не подключён.'}
    if not binding:
        return result
    approved = scope(binding)
    profile = digest({'owner': approved['owner_id'], 'bot_id': approved['bot_id'], 'mode': approved['mode']})
    result.update(mode=approved['mode'], status='waiting', description='Ожидаем подтверждение работы обработчика.')
    with store.transaction() as session:
        store.check_audit(session)
        row = session.execute(select(Audit).where(
            Audit.event['kind'].as_string().in_(['telegram_service_started', 'telegram_service_heartbeat',
                                                'telegram_service_stopped', 'telegram_poll_failed']),
            Audit.event['profile'].as_string() == profile,
            Audit.event['revision'].as_string() == store.settings.source_revision,
        ).order_by(Audit.sequence.desc()).limit(1)).scalar_one_or_none()
        if row is None:
            return result
        event = row.event
        age = (store.now(session) - datetime.fromisoformat(event['time'])).total_seconds()
        if age < 0 or age > 60:
            result.update(status='stale', description='Свежего подтверждения работы нет.')
        elif event['kind'] == 'telegram_service_stopped':
            result.update(status='stopped', description='Обработчик Telegram остановлен.')
        elif event['kind'] == 'telegram_poll_failed':
            result.update(status='degraded', description='Обработчик сообщил об ошибке связи.')
        elif (event['kind'] == 'telegram_service_heartbeat'
              and event.get('connection_digest') == approved['connection_digest']
              and event.get('bot_id') == approved['bot_id']):
            result.update(status='polling', live_connected=approved['mode'] == 'live',
                          description=('Обработчик получает сообщения.' if approved['mode'] == 'live'
                                       else 'Работает тестовый HTTP-адаптер; настоящий бот не подключён.'))
    return result
