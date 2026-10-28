"""Fixed owner navigation; buttons invoke existing read-only commands only."""

BUTTONS = (
    ('📁 Проекты', '/projects'), ('📥 Запросы', '/requests'),
    ('🧪 Результаты тестов', '/tasks'), ('ℹ️ Помощь', '/help'),
)


def keyboard():
    """Return a fresh Bot API ReplyKeyboardMarkup, never caller-defined actions."""
    return {'keyboard': [[{'text': label} for label, _ in BUTTONS[start:start + 2]]
                         for start in (0, 2)], 'resize_keyboard': True, 'is_persistent': True}
