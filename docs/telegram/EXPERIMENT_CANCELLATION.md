# Отмена первого AI-эксперимента через Telegram

Cloud-продолжение [PR #45](https://github.com/v71369322-lang/ai-command-center/pull/45).
На действующем VPS этой команды пока нет. Предыдущие pinned targets не включают
эту доработку; доставка требует нового именованного пакета и exact approval.

Operator profile `--release first-experiment-cancel` закрепляет переход d932baaf →
`a5d867cb734a4954926a4e77c71e6f5be217057c`. Один кандидат содержит предшествующие
gateway/readiness/snapshot/notification функции и cancel. Private file bindings
и readiness opt-in обязательны; прежние семь source targets сохранены.
Operator checkout закрепляется отдельно от application SHA. Host prepare и exact
candidate apply остаются отдельными разрешёнными владельцем этапами.

## Использование после доставки

`/cancel_experiment` без аргументов в личном чате владельца запрашивает отмену
единственной фиксированной задачи первого AI-эксперимента. Команда использует
прежнюю F1 cancel: approval отзывается, WAITING_APPROVAL/READY становятся
CANCELLED, выполняющиеся или требующие сверки задачи — CANCEL_REQUESTED.
Это подтверждение сохранённого намерения; фактическая остановка исполнителя
проверяется отдельно. Текущий снимок доступен через `/experiment`.

Уже выполненный вызов может быть оплачен. Расходы, финансовые grants и спорные
резервы не меняются; неопределённый исход остаётся предметом сверки и не получает
права на повтор. Отмена не обещает возврат денег. Команда доступна при обычной
остановке/recovery и не снимает их. Общие `/cancel UUID` и `/stop` сохранены.

Если задачи при получении команды не было, ничего не отменяется. Команда не
переносится на будущую задачу. Для завершённой или заблокированной задачи
сохраняются результат и история; новое исполнение не создаётся.

## Привязка и атомарность

При приёме команды прежний append-only audit фиксирует UUID и payload hash
точной owner request key/payload/creation записи. Inbox intent остаётся фиксированным.
Применение проверяет receipt, profile, source, fingerprint, тип и состав binding,
исходный UUID/payload и срок 120 секунд. Замена задачи под тем же request key,
смена source, изменение JSON или истёкшее получение не разрешают отмену другой задачи.
После истечения команды нужно отправить новую команду; автоматического переноса нет.

Проверки receipt, прежний F1 cancel, audit и завершение inbox/reply выполняются
в одной существующей Control/admission transaction. Ошибка постановки ответа
откатывает и отмену; восстановление может применить ещё действующий receipt один раз.
Одновременный дубль и перезапуск не повторяют действие. Потерянная отправка
подтверждения сохраняется UNCERTAIN и не пересылается автоматически.

`Store._cancel_locked` — внутренняя композиция существующего cancel, с теми же
role/operator ownership правилами. Новая permission system, схема или gateway
не добавляются. Проверка личности задачи отделена от финансового snapshot:
неопределённый ledger не мешает отзыву действий уже установленной задачи.
Команда не создаёт Gateway/HTTP clients, не читает credentials, не выполняет
provider requests, reconciliation, публикацию или runtime retry.

## Проверки и границы

PG/strict-mock tests покрывают состояния задачи, no-task-at-intake, concurrent
duplicates/restart, crash rollback, срок/source/receipt/UUID/numeric JSON tampering,
private-owner checks, остановку/recovery и неизвестную доставку ответа.
Отмена во время mock HTTP сохраняет полученную usage либо спорный резерв;
следующий вызов блокируется прежним Gateway. Это не настоящий AI-вызов.

Последний локальный расширенный scope:344 passed /1 failed /4 deselected /1
существующий Starlette-httpx warning;32 новых cancel cases входят в344.
Оставшийся прежний container case остановился на executor_revision_mismatch;
две coding container cases предыдущего scope — на coding_image_revision_mismatch.
Это старые local images; guard не ослаблялся. Четыре deselected cases также
требуют fresh-source containers. Итоговое исполнение этих cases — в CI Draft PR.
Ruff/OpenAPI/current-runtime-secret guard/diff check PASS; locked audit:64 Python
dependencies,0 Python/npm advisories,0 Bandit MED/HIGH,92 retained reviewed LOW.
Локальные source checks выполнены до source commit, итоговый SHA проверяется в CI.
Named staging suite:405 passed для всех восьми profiles; это отдельный
infrastructure scope, пересекающиеся наборы не суммируются.
Контейнерные tests требуют свежих exact-source images; старые local images не
переименовываются. Cloud rootful tests не подтверждают rootless VPS/systemd,
физический iPhone, баланс провайдера или разрешение платного запуска.
