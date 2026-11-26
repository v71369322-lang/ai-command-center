"""Hold explicit mixed dictation intact; never guess a batch or its authority."""
import re

from .models import TelegramInbox
from .store import Denied
from .telegram_requests import captured_text


def multiple_requests(value):
    # Quoted examples are data. Missing/ambiguous structure is not a batch plan.
    text = re.sub(r'«[^»]*»|"[^"\n]*"', ' ', value)
    imperative = r'(?<!\w)(?:(?:запиши|сохрани)(?: мне)?\s+(?:задачу|идею|заметку)|напомни(?: мне)?|(?:создай|добавь|запиши)(?: мне)?\s+(?:встречу|событие)|отдельн(?:ая|ую)\s+(?:идея|идею|задача|задачу|заметка|заметку))\b'
    positions = {match.start() for match in re.finditer(imperative, text, re.I)
                 if not re.search(r'\bне\s*$', text[:match.start()], re.I)}
    for match in re.finditer(r'(?<!\w)(?:идея|задача|заметка)\s*:', text, re.I):
        positions.add(match.start())
    return len(positions) > 1


def hold_locked(bridge, session, iid, value):
    from .assistant_policy import assistant_only
    if not assistant_only() or not multiple_requests(value):
        return False
    row = session.get(TelegramInbox, iid)
    if row is None or row.profile != bridge.profile:
        raise Denied('mixed_inbox_owner_scope')
    if captured_text(session, row, states=frozenset({'RECEIVED', 'NEEDS_PLANNING'})) != value:
        raise Denied('mixed_inbox_source_changed')
    # SAME immutable original/accepted transcript. No invented owner updates or
    # synthetic children, grants, dates, project assignments or execution tasks.
    row.state = 'NEEDS_PLANNING'
    bridge.store.audit(session, 'personal_mixed_request_held', 'owner', profile=bridge.profile,
                       request_id=iid, request_fingerprint=row.fingerprint)
    number = iid.rsplit(':', 1)[1]
    bridge.enqueue(session, iid + ':reply',
        f'Похоже, в сообщении несколько поручений. Весь текст сохранён во входящих: №{number}.\n'
        'Отдельные задачи, напоминания и события ещё не созданы. '
        'Пока обработаю по одному: отправьте каждое отдельным сообщением.\n'
        f'Открыть исходный текст: /request {number}')
    return True
