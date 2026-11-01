# Единый процесс подготовки подключения проекта

Владелец попросил один крупный cloud-этап без компьютера поверх PR #63.
Реализован полный жизненный цикл **декларативного черновика** в Commander:
сводка четырёх проектов → редактирование → предпросмотр → сохранение → история
→ просмотр версии → восстановление в новую версию. Веб и Telegram используют
одно хранилище и одни проверки версии. Реальные проекты/VPS здесь не подключаются.

## Что может сделать владелец

В прежней панели «Проекты и запросы» появилась сводка заполнения черновиков.
В раскрытом плане проекта — форма, обязательные внешние проверки и история.
Пять сведений: полный SHA выбранного кода, тип среды проверки (Python/Node/оба),
способ проверки доставки (ручной/существующий канал), метка серверной площадки
и до восьми критериев результата. Репозиторий фиксирован существующим каталогом;
выбрать иной repository, credential file, shell command, URL или permissions нельзя.
Метка площадки — декларация, не адрес/identity работающего сервера.

Можно сохранять неполный черновик. «Заполнено 5 из 5» означает только полноту:
ready_for_operator_review=true, execution_ready=false. Во всех ответах
scope=SETUP_DRAFT_ONLY, execution_connected=false, external_checks_performed=false,
actions_enabled=[]. Привязка репозитория, изолированная проверка, привязка доставки
и отдельное разрешение задачи остаются обязательными даже у полного черновика.

Предпросмотр не сохраняет черновик и показывает изменённые поля и новую полноту.
После изменения поля прежний preview сбрасывается. Неподтверждённое сохранение
блокирует следующую запись до явного чтения сохранённой версии. Автоповтора POST
нет. Ошибка preview позволяет исправить поля; stale version требует загрузить
актуальный черновик. Историческая версия доступна только для чтения; её
восстановление создаёт новую запись, не переписывает прошлую. Версия 0 — исходный
пустой черновик. Logout/закрытие отменяют ожидающие client requests.

## HTTP и Telegram

Все новые HTTP routes требуют прежнюю owner identity/CSRF/origin/revocation:

- GET /api/project-setup — сводка четырёх проектов;
- GET /api/projects/{id}/setup[?version=N] — текущая/историческая версия и история;
- POST /api/projects/{id}/setup/preview — expected_version + draft;
- POST /api/projects/{id}/setup — expected_version + draft + UUIDv4 operation_id;
- POST /api/projects/{id}/setup/restore — expected_version + target_version +
  точный target_digest + UUIDv4 operation_id.

Прежние inbox и connection-plan API сохранены. OpenAPI расширен новыми routes
и strict extra-forbid models; migrations/dependencies/roles не добавлены.

Telegram использует private-owner commands:

- `/setup` и `/setup project-id [версия]` — выбор/просмотр;
- `/setup_set project-id ожидаемая-версия поле значение` — изменить одно поле;
- `/setup_clear project-id ожидаемая-версия поле` — очистить поле;
- `/setup_history project-id` — последние версии;
- `/setup_restore project-id ожидаемая-версия целевая-версия` — восстановить.

Поля команд: revision, verification, delivery, target, acceptance. Пример:
`/setup_set lnauto 0 verification python_node`. Критерии — текстовые данные,
не команды; многострочный acceptance заменяет список, а не запускает вложенные
`/stop`/approval strings. Неизвестные IDs/поля/значения отклоняются до capture.
История Telegram ограничена пятью строками, критерии выводятся кратко с сохранением
полного текста в защищённом черновике; character/JSON limits не расширены.

## Хранение, конкуренция и права

Existing PostgreSQL/Audit остаётся authoritative. Один append-only
project_setup_draft_changed event хранит normalized draft, project-bound digest,
исходное действие и его hash, строгую версию и operation UUID. Лимит 500 изменений
на все проекты, до 12288 canonical JSON bytes на документ; каждый из 8 критериев
ограничен 200 символами и 400 UTF-8 bytes. Нет автоматического удаления истории.
Новых таблиц/пользователей/секретных файлов или второго механизма authority нет.

Readers проверяют целую F1 audit chain и воспроизводят save/patch/clear/restore
по предыдущим версиям. Проверяются schema, actor/task/source/time/types,
порядок версий, UUID namespace, hashes, canonical draft и историческая цель
restore. Текущие известные credentials и типовые key patterns проверяются
повторно; это не универсальный DLP. Ключи и клиентские данные вводить нельзя.
Непосредственно перед Bot API заново проверяется и queued reply: значение,
ставшее известным credential после постановки ответа в очередь, не отправляется.

Все writers используют прежнюю F1 Control transaction/lock. Параллельные
изменения одного expected_version дают одного победителя; stale write не
перезаписывает новую версию. Повтор UUID с тем же действием возвращает прежний
receipt, с другим проектом/содержимым отклоняется. Исторические metadata
сохраняются при смене версии приложения и проверяются по schema 1; это не
перенос execution approvals на новый source.

Telegram operation UUIDv5 выведен из private profile/inbox namespace; HTTP
принимает только UUIDv4. Перед записью и атомарным finish повторно сверяются
pending row/fingerprint/owner receive anchor/source/profile и connection/runtime
guard. Черновик, DONE и queued reply фиксируются одной транзакцией. Ошибка
reply/отзыв guard откатывают metadata; UNCERTAIN send не повторяет сохранение
или отправку. Обычная остановка остаётся действующей; она не мешает metadata.

Task/Approval/ExternalGrant/worker Outbox, leases/fencing, reserves и расходы
не меняются. Source-pinned execution, verifier и publisher не читают эти drafts
как полномочия. Никаких GitHub/OpenAI/VPS probes или сетевых вызовов ради формы.

## Отображение и совместимость

API /state выдаёт минимальную проекцию новых audit events для всех ролей:
kind/details_redacted, исходные sequence/digest/checkpoint сохранены. Raw draft
и action input доступны только screened owner setup readers; оператор не
получает их через общую ленту. Это проекция, не полный текст проверяемого audit
event. В самом PG/backup полные audit records остаются без изменений.

Старые API-readers, раскрывающие raw audit, не являются совместимой границей
приватности для этих новых drafts. Совместимость migrations/models сама по себе
не разрешает такой downgrade. Перед будущей host-доставкой нужна проверка всего
набора readers. В текущий VPS новые рабочие drafts не записывались.

Все 12 release pairs, frozen recovery runtime bf91c05 и его build-only пакет
сохранены. Новый source не входит в этот frozen build и не имеет подготовленного
host apply. Первый host-шаг по-прежнему — разрешённая свежая проверка PR #61,
реальный recovery тест, затем отдельное подключение одного проекта. Этот
cloud-процесс не закрывает VPS/MFA/offsite/iPhone/live-provider acceptance.

## Проверки

Настоящий локальный PG/API/Chromium 320/390 и strict fake Bot API проверяют полный
цикл, preview без записи, межканальные stale версии, idempotency/conflicts,
rollback/response loss/restart, source/owner/CSRF boundaries, malformed/secret
inputs, malformed audit with valid chain, privacy projection, XSS и отзыв
connection до commit. Existing service-container smoke расширен полным
Telegram-путём до полного draft и восстановления, сохраняя coding task 15,
callback 100/101, batch limit 20 и 40 циклов. Это synthetic cloud proof.
Точные HEAD, merge-ref, counts и окончательный CI фиксируются в одном Draft PR.

Следующий этап — [единая карточка запроса](REQUEST_REVIEW.md): setup, назначение
и предложение плана читаются вместе, без нового хранилища или grant.
