"""Fixed owner navigation; buttons invoke existing read-only commands only."""

BUTTONS = (
    ('📁 Проекты', '/projects'), ('📥 Запросы', '/requests'),
    ('🔔 Центр внимания', '/attention'), ('⏰ Напоминания', '/reminders'),
    ('🎙 Голос', '/voice'), ('🧩 Система', '/system'),
    ('🧪 Результаты тестов', '/tasks'), ('ℹ️ Помощь', '/help'),
)


def keyboard():
    """Return a fresh Bot API ReplyKeyboardMarkup, never caller-defined actions."""
    from .assistant_policy import assistant_only
    buttons = tuple(item for item in BUTTONS if item[1] not in {'/tasks', '/system'}) if assistant_only() else BUTTONS
    return {'keyboard': [[{'text': label} for label, _ in buttons[start:start + 2]]
                         for start in range(0, len(buttons), 2)],
            'resize_keyboard': True, 'is_persistent': True}
