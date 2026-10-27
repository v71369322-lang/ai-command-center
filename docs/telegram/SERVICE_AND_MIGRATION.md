# Telegram polling service и отдельная миграция

База: PR #22, `feat/telegram-mobile-inbox`,
`73a26a7b76b618c2673d75009de17c28a8b89d4c`.
Ветка: `feat/telegram-service-migration`; цепочка #21 → #20 → #17 сохранена.
VPS, Windows, настоящие credentials и бизнес-системы не использовались.

## Работающий обработчик

`command_center.telegram_service` — постоянный процесс, использующий F1
tasks/approvals/Outbox/audit. `telegram_transport` реализует настоящий фиксированный
Bot API HTTP-клиент; в тестах транспорт исключительно MockTransport.

* Один poller данного бота в одной authoritative PostgreSQL: session advisory
  lock проверяется до и после HTTP. Потеря lock/БД блокирует принятие команд.
  Это не глобальный fencing двух разных копий БД и не независимый аварийный канал.
* Токен читается только из приватного regular file, без symlink/hardlink,
  с владельцем UID процесса, без group/world permissions; родительский каталог
  также приватный. CLI, задачи и панель не принимают значение токена.
* Entrypoint требует только f1_app DB credential. Redis, API-owner и PG-admin
  credentials ему не нужны. Сервис не запускает Docker или executor сам.
* Default mode disabled. Запуск требует точного digest защищённой connection
  configuration и совпадения Git SHA. Изменение/отзыв config или ротация ключа
  останавливают прежний клиент. Это разрешение внешнего подключения, не новый
  механизм task authority: исполнение разрешается существующим F1.
* Проверяются getMe, bot_id и отсутствие активного webhook. Сервис не удаляет
  чужой webhook. Разрешены только getMe/getWebhookInfo/getUpdates/sendMessage
  владельцу/answerCallbackQuery. Нет произвольного HTTP, URL-кнопок, групп,
  файлов, voice, redirect или открытого входящего порта.
* До 20 Update за цикл, 8 KiB request, 64 KiB response, HTTP timeout 25 секунд.
  Read retries ограничены тремя. retry_after соблюдается; слишком большой
  или непонятный rate limit останавливает процесс. Спорные send не повторяются.
* Callback exact version/hash/epoch/revision/expiry/nonce остаётся в F1.
  Ack имеет durable audit intent; потеря его ответа не откатывает approval
  и не вызывает повтор исполнения.
* RECEIVED восстанавливается из DB даже без remote redelivery. Intent hash
  привязан к audit. Старый pending source требует сверки; истёкшее подтверждение
  отклоняется. Bot/owner/mode profile стабилен при обновлении/ротации.
  Учтён документированный случай случайного меньшего Update ID после недели
  без сообщений. Старые Update не становятся новой работой.
* Токен в URL HTTP-библиотеки редактируется logging filters; наружу выходят
  стабильные error codes. Bot credentials во входном тексте не сохраняются.
* SIGINT/SIGTERM заканчивают работу без новых разрешений. Нет auto resume F1,
  schema bootstrap, постоянного платного provider или запуска shell из текста.

## Миграция

`command_center.telegram_migration` имеет read-only plan и явный apply с
--approved-plan, --container, --backup-file и --key-file (путь, не значение).
Требуются admin binding, halted admission, отсутствие active/cancel-requested/
reconciling executions и подключений f1_app/f1_runtime, известные core schema
и constraints, валидная audit chain. Посторонние таблицы/views запрещены.
Docker PostgreSQL сверяется с DB connection по system_identifier.

Plan digest связывает source SHA, кластер, DB, audit anchor и hashes всех строк
восьми core tables. Под F1 maintenance lock создаётся pg_dump, шифруется
существующим AES-GCM и записывается новым 0600 файлом с fsync файла/каталога.
Обратное чтение/расшифровка и hash проверяются. До DDL копия восстанавливается
в другом networkless контейнере pinned PostgreSQL: UID 999, read-only rootfs,
cap_drop ALL, no-new-privileges, CPU/RAM/PID limits, tmpfs, без host mounts,
портов и socket. Сравниваются все исходные строки. Неподтверждённое удаление
restore-контейнера блокирует применение.

Одна транзакция создаёт ровно три Telegram tables, grants f1_app, запрещает
runtime role доступ, проверяет старые данные и записывает audit receipt.
Повтор того же плана не создаёт вторую миграцию/backup. Ошибка DDL откатывает
все новые таблицы; backup остаётся. Drop/down migration и restore поверх primary
отсутствуют. Локальная копия не является offsite, RPO/RTO этим не доказаны.

По умолчанию toolbox использует rootless socket текущего оператора;
cloud-rootful adapter явно задан только в тестах. Доступ к Docker и PG admin
нужен доверенному одноразовому migration operator, **не** Telegram-сервису.
В будущем он может выполняться из проверенного broker image в control network
с временными socket/admin/backup bindings. Эти bindings нельзя выдавать API,
worker, coding agent или executor.

## Практическая проверка и восстановление облачной работы

До потери исполнительной среды 2026-10-27 прошли **88 целевых тестов**:
37 service/transport, 9 migration и 42 существующих Telegram/browser/password.
Отдельно прошли 32 infrastructure tests, Ruff, OpenAPI и TypeScript/Vite.
В целевых тестах настоящий PG/Redis/Docker executor, но fake Bot API.
Прежний security gate дал 0 Python/npm advisories и 0 MEDIUM/HIGH; финальный
security результат после последних правок нужно брать из CI нового SHA.
Одно предупреждение Starlette/httpx не скрывается.

Проверены полный demo → callback → F1 approval/Redis → executor → verifier →
одно уведомление, restart, response loss, in-flight leadership loss, expired
pending, source change, credentials boundaries, 401/429/503, audit corruption.
На отдельной старой PG schema: preservation задач/approvals/outbox/owner sessions/
audit/budget, реальный isolated restore, corrupt backup, wrong DB/plan,
partial DDL rollback, active connections и отказ cleanup.

`scripts/telegram_service_smoke.py` включён в verify_cloud.sh: отдельный
ограниченный контейнер, реальная PG, mock HTTP, два цикла; проверяются отсутствие
socket/портов/admin/API-owner/Redis credentials и подтверждённый cleanup.
Требуются clean checkout и pinned image label. До сокращения ненужных secret
bindings контейнерная проверка прошла; обновлённый минимальный профиль проверяет CI.

При сбое exec-server основной checkpoint уже был в GitHub:
`a7929b117d52dd64b74d7ae403640f7a46e83016`.
Локальные d8e1ef9/f60ab45 и незакоммиченные правки нельзя считать опубликованными.
Их записанные изменения восстановлены поверх проверенного remote checkpoint
штатными GitHub Git-object tools; это не новый проект или новая архитектура.
GitHub Actions нового коммита — обязательная повторная проверка восстановленных файлов.
Результаты не суммируются с полным suite. Токены в чат/PR/Git не передавались.

Точечный nosec B106 касается только публичного пути /run/telegram/token в smoke
configuration, а не значения credential. Общие secret/static gates не отключены.
Security summary в CI теперь печатает только SHA и числовые результаты, без значений
ключей, чтобы доказательства не зависели от потерянного workspace.

## Оставшиеся границы

Migration gate обычного deployment **не изменён**. Миграция не переписывает
deployment.json и не разрешает generic update между разными migration hashes.
Нужно отдельно проверить включение сервиса в строгий release profile и
контролируемый переход deployment receipts с учётом миграции. Ручное изменение
state/compose up вместо interlocked deployment запрещено.

API /api/telegram/status пока показывает disabled: runtime health отдельного
сервиса ещё не подключён к панели. Это завершается вместе с release profile.
Нужны реальные protected secret binding, подтверждённый owner ID и разрешение
на live calls/установку. Образец telegram-connection.disabled.json выключен:
его IDs/SHA — фикстуры. Само добавление токена ничего не включает.

Cloud-rootful проверки не доказывают rootless/systemd/reboot/TLS настоящего VPS
или работу Safari/Telegram на iPhone. Голос, AI-планирование, CRM и реальные
AI/GitHub provider calls остаются выключенными.

Контракты:
https://core.telegram.org/bots/api#update
https://core.telegram.org/bots/api#getupdates
https://core.telegram.org/bots/api#answercallbackquery
