"""Hold explicit mixed dictation intact; never guess a batch or its authority."""
import re

from .models import TelegramInbox
from .store import Denied
from .telegram_requests import captured_text


ORDINALS = ('первое', 'второе', 'третье', 'четвёртое', 'пятое', 'шестое',
            'седьмое', 'восьмое', 'девятое', 'десятое')


def enumeration_mask(value):
    """Keep offsets while masking nested quotes; incomplete quotes refuse."""
    pairs = {'«': '»', '“': '”'}
    stack, quote = [], None
    result = []
    for char in value:
        quoted = bool(stack or quote)
        if quote:
            if char == quote:
                quote = None
        elif char in pairs:
            stack.append(pairs[char])
        elif char in pairs.values():
            if not stack or stack.pop() != char:
                return None
        elif not stack and char in {'"', "'"}:
            quote = char
        result.append(' ' if quoted or stack or quote else char)
    return None if stack or quote else ''.join(result)


def enumeration(value):
    """A complete explicit 1..N list only; source offsets include its headings."""
    text = enumeration_mask(value)
    if text is None:
        return []
    words = list(re.finditer(r'(?<!\w)(?:и\s+)?(' + '|'.join(ORDINALS) +
                            r'|четвертое)(?:\s*[:.)—-]\s*|\s+)', text, re.I))
    numbers = list(re.finditer(r'(?m)^[ \t]*([1-9][0-9]{0,2})[.)][ \t]+', text))
    if bool(words) == bool(numbers):
        return []
    matches = words or numbers
    if not 2 <= len(matches) <= 8 or value[:matches[0].start()].strip():
        return []
    labels = ([ORDINALS.index(m[1].lower().replace('четвертое', 'четвёртое')) + 1 for m in words]
              if words else [int(m[1]) for m in numbers])
    if labels != list(range(1, len(matches) + 1)):
        return []
    # Dates, rankings and quoted examples are not task enumeration. Unknown
    # or negated actions can remain visible, but never acquire a save button.
    starter = (r'(?:купить|позвонить|проверить|заказать|подготовить|забрать|отправить|оплатить|'
               r'задача|идея|заметка|напомни|создай|добавь|запиши|сохрани|не|планирую)\b')
    if any(not re.match(starter, text[m.end():], re.I) for m in matches):
        return []
    for match, end in zip(matches, [m.start() for m in matches[1:]] + [len(value)]):
        extra = explicit_markers(text[match.end():end])
        if extra and extra != [0]:
            return []
    return matches


def item_content(value, start, end):
    """Strip a heading for parsing only, after validating the complete source."""
    heading = next((m for m in enumeration(value)
                    if m.start() == start or (start == 0 and not value[:m.start()].strip())), None)
    return value[heading.end() if heading else start:end]


def request_markers(value):
    listed = enumeration(value)
    if listed:
        return [m.start() for m in listed]
    return explicit_markers(value)


def explicit_markers(value):
    # Quoted examples are data. Missing/ambiguous structure is not a batch plan.
    text = re.sub(r'«[^»]*»|"[^"\n]*"', lambda m: ' ' * len(m[0]), value)
    imperative = r'(?<!\w)(?:(?:запиши|сохрани)(?: мне)?\s+(?:задачу|идею|заметку)|напомни(?: мне)?|(?:создай|добавь|запиши)(?: мне)?\s+(?:встречу|событие)|отдельн(?:ая|ую)\s+(?:идея|идею|задача|задачу|заметка|заметку))\b'
    all_matches = list(re.finditer(imperative, text, re.I))
    matches = [m for m in all_matches
               if not re.search(r'\bне\s*$', text[:m.start()], re.I)]
    positions = {m.start() for m in matches}
    for match in re.finditer(r'(?<!\w)(?:идея|задача|заметка)\s*:', text, re.I):
        if (not any(m.start() <= match.start() < m.end() for m in all_matches)
                and not re.search(r'\bне(?:\s+(?:запиши|сохрани)(?:\s+мне)?)?\s*$', text[:match.start()], re.I)):
            positions.add(match.start())
    return sorted(positions)


def multiple_requests(value):
    return len(request_markers(value)) > 1


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
    from .mixed_review import issue_locked
    if issue_locked(bridge, session, row, value):
        return True
    number = iid.rsplit(':', 1)[1]
    bridge.enqueue(session, iid + ':reply',
        f'Похоже, в сообщении несколько поручений. Весь текст сохранён во входящих: №{number}.\n'
        'Отдельные задачи, напоминания и события ещё не созданы. '
        'Пока обработаю по одному: отправьте каждое отдельным сообщением.\n'
        f'Открыть исходный текст: /request {number}')
    return True
