# Снятие обычной остановки с телефона

Отдельная cloud-доработка поверх PR #36, без обновления VPS. Исходная база
operator branch: `364c5eb4b44ad4ab743cacd9ae1d204866bd0d6c`; приложение на VPS
после F34 — `b2e71fe073f3109e639dac43496884905ce86d9f`.
До отдельной доставки нового приложения команда `/resume` там недоступна.

## Поведение после будущего обновления

1. Владелец пишет `/resume` в личном чате с подключённым ботом.
2. При обычной остановке бот показывает одну кнопку подтверждения. Запрос
   действует 120 секунд от durable receipt исходного Update; restart не
   продлевает срок. Уже работающая система не меняется. Recovery не даёт кнопку.
3. Нажатие владельцем реально доставленной кнопки снимает только обычную
   остановку. Старые задачи не перезапускаются. `/coding_demo` или другая новая
   ограниченная задача задаётся отдельно, после подтверждённого ответа.
4. `/stop` остаётся прежней остановкой F1. Аргументы `/resume --force`, текстовые
   инструкции, произвольные модели/репозитории/URL не расширяют команду.

Нет публичной веб-панели, новых сетевых портов, SSH, secrets, платных вызовов,
доступа к CRM или автоматического deployment. Telegram использует прежний
owner/private-chat binding. Это не подключение IdP/MFA: доверие к учётной записи
Telegram остаётся границей данного канала, как у прежней команды `/stop`.

## Общая F1-операция и checkpoint

Внешний `Store.resume(actor, epoch, checkpoint_digest)` сохраняет exact latest
checkpoint, owner role, halted/recovery, epoch и отсутствие RUNNING/VERIFYING/
RECONCILING/CANCEL_REQUESTED/SECURITY_BLOCKED. Его тело вынесено без изменения
условий в `_resume_locked`, вызываемый из того же `Store.transaction()` с
глобальным PostgreSQL lock. HTTP/OpenAPI контракт не изменён.

Telegram — второй trusted caller этой же операции, не второй механизм F1.
Под lock он проверяет receipt/fingerprint исходного Update, одноразовый random
callback, профиль владельца/бота, source revision, expiry, audit-issued delivery,
её body hash, SENT и наблюдавшийся message_id, exact approved connection digest.
Повторное подключение с другим credential reference не переносит старую кнопку.
Карточка/consumption записываются
в прежний append-only Audit, транспорт — в прежние Inbox/Delivery. Новых таблиц
и миграции нет.

Пока владелец читает карточку, Telegram сам добавляет heartbeat и delivery events.
Поэтому карточка фиксирует anchor sequence/digest; перед вызовом F1 разрешена
проекция к latest head только через закрытый список transport bookkeeping в
`telegram_control.TRANSPORT_EVENTS`, с той же source revision. Любые task,
permission, budget, control/security, project или неизвестные audit events
делают подтверждение устаревшим. Список не означает разрешение действий по
тексту сообщения; обычные запросы по-прежнему только сохраняются.

Затем общая F1-операция снова проверяет цепочку и exact latest head, recovery,
epoch и незавершённые состояния. Resume, consumed marker, DONE исходного Update
и queued reply коммитятся атомарно. Ошибка до commit откатывает их вместе.
Duplicate/restart не создаёт второй эффект. Неопределённая отправка кнопки
не считается SENT и не разрешает подтверждение; автоматического resend нет.
Неопределённая отправка результата не отменяет уже подтверждённый commit.

Если checkpoint изменился или срок истёк, требуется новый `/resume` и новая
кнопка. Recovery/неопределённые исполнения требуют отдельной сверки; команда их
не исправляет, не снимает SECURITY_BLOCKED, не освобождает спорные резервы,
не возобновляет старые approvals и не выдаёт ExternalGrant.

## Проверки

Новые PG + mock HTTP tests проверяют запрос без эффекта, успешное подтверждение,
отменённые задачи/бюджет/approval, exact HTTP checkpoint, duplicates/concurrency,
restart/atomic rollback/expiry, чужого отправителя, группу/forward/message,
подмену body, неопределённый sendMessage, source change, PostgreSQL outage,
audit corruption, recovery и все пять опасных task states. Источник поддельного
HTTP — documented Telegram Bot API shapes, реального Telegram контакта нет.

Локально первый итоговый набор — 40 passed; после проверки срока ещё перед
commit и clock rollback/connection reapproval guards — 43 новых проверки.
Прежний расширенный Telegram набор на checkpoint 48cbea7: 270 passed /1 прежний
Starlette/httpx warning. Его первый запуск дал 264 passed /3 failed на старых
images bbd4d08; после сборки exact images 48cbea7 все 270 прошли. Pinning не
менялся. 40/43 входят в соответствующие расширенные наборы, не суммируются.
Отдельно 143 infrastructure, Ruff/OpenAPI/TypeScript/Vite/security/dependency
проверки прошли. Полный CI final HEAD/merge-ref проверяется отдельно в PR;
старые локальные images не переименовываются в новую source revision.

`scripts/telegram_service_smoke.py` дополнен отдельной фазой normal stop →
fake HTTP request → SENT confirmation → callback → actual PG/F1 resume в том же
изолированном service container. Прежний coding repair/verifier/mock PR smoke
сохраняется. Rootless/systemd/VPS/iPhone этой доработки требуют будущей host
приёмки и не заменяются облачным rootful тестом. Точные counts/CI — в PR.
