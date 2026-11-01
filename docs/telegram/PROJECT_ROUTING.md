# Назначение проекта из Telegram

Продолжение PR #27 (ee08cb6), отдельная ветка feat/telegram-project-routing.
Вечерний F32-пакет 316dc16 не меняется автоматически. VPS и реальные API
этой разработкой не подключаются.

После отдельного подключения бота доступны:

- `/projects`: четыре project IDs и подсказка.
- `/request 123`: исходный текст, выбранный проект и версия назначения.
- `/assign 123 lnauto 0`: назначение проекта при ожидаемой версии 0.
- `/assign 123 none 1`: снятие назначения при ожидаемой версии 1.

IDs: command-center, vanilla-sugar, lnauto, capital-lab. Версия обязательна:
устаревшее сообщение не должно отменить более новое назначение в панели.
Это метаданные NEEDS_PLANNING, не разрешение на AI/CRM/execution.

Следующая cloud-доработка добавляет [выбор проекта inline-кнопкой](PROJECT_PICKER.md)
под capture receipt и `/request`: ручной ввод ID/версии больше не нужен для этого
пути. Прежняя команда `/assign` и её проверки сохраняются; на VPS новая версия
автоматически не устанавливается.

Используется тот же project_inbox.classify, optimistic version и audit ledger,
что и в API. Telegram request ID всегда выводится из текущего connection profile;
произвольный чужой inbox ID не принимается. Проверки owner/private-chat,
connection/leadership/source/recovery/audit/secret boundaries сохраняются.

Стандартный UUIDv5 от durable inbox ID — стабильный operation ID (не credential).
В одном существующем F1 transaction/lock фиксируются assignment audit, DONE
входящей команды и исходящий receipt. Ошибка подтверждения/отзыв откатывает всю
операцию. Crash до commit восстанавливается resume_pending; после commit
повтор Update не даёт второго назначения. Старое pending с иной version
отклоняется. Неопределённый send не повторяется вслепую.

HTTP API по-прежнему требует UUIDv4 и не принимает внутренний callback.
Внутренний transaction callback доступен только доверенному Python-коду bridge;
это не новый внешний endpoint и не изменение механизма полномочий F1.
Новых таблиц, migrations, dependencies или host rights нет.

Тесты: actual PostgreSQL + mock HTTP, concurrent/restart/stale/revocation/rollback;
service-container smoke выполняет capture → read → assign → read с fake Bot API.
Реальные iPhone/Telegram/VPS этой проверкой не подменяются. Итоговые результаты
и SHA приводятся в отдельном Draft PR.
