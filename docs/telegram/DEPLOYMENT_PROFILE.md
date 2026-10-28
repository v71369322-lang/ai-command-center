# Telegram: профиль установки и точный переход схемы

База разработки — PR #23, SHA `03ab17c97cb8f472861d753997e31b336412adf7`.
Существующая цепочка зависимостей и generic deployment gate сохранены.
В этом изменении нет SSH, установки на VPS, реальных токенов или Bot API calls.

## Подтверждённое состояние VPS по выводу владельца

28 октября 2026 владелец выполнил подготовленный F31 update. Вывод содержал
`F31_UPDATE_OK` и успешный postcheck для закрытого синтетического контура.
Пакет `1e151b2953b6debb4bb05096fba20aa6c740665015f31479a50fd25c6ef80106`
соответствует source `4cc6ec46bf461d65958f013bb23ac2234b9a7fd3`.
На присланных скриншотах видны вход по паролю, безопасная задача SUCCEEDED и
F2 mock repair: ошибка первой проверки, успешная вторая, подготовленный mock PR.
Это owner-provided evidence, не независимый shell-доступ и не реальный AI-запуск.
Исходный F30 package/source сохраняются, реальные интеграции не принимались.

## Сначала код и схема с выключенным Telegram

Обычный `deployment update` по-прежнему отвергает другой migration_hash.
Нельзя вручную менять deployment.json, подменять hash или запускать compose up.
Новый локальный `command_center.telegram_transition` допускает только переход
из проверенного password release `4cc6ec4` и его точного models/admin fingerprint
к известной схеме трёх Telegram tables. Смена PG/Redis images, UID, data-root,
owner login или включение live Telegram одновременно с миграцией запрещены.

1. После отдельно разрешённой доставки/сборки подготовить новый bundle обычным
   `deployment prepare`, с тем же state и password origin; **без** Telegram flag.
2. `telegram_transition stage --bundle NEW --approved-bundle NEW_DIGEST
   --approved-previous CURRENT_DIGEST`: проверяет обе версии и images, берёт
   deployment lock, останавливает admission, доказывает отсутствие исполнений,
   создаёт зашифрованную копию, сохраняет durable intent и останавливает приложения.
   PostgreSQL/Redis и данные сохраняются. Возвращает конкретный plan_digest.
   На этом шаге панель временно недоступна; stage не является read-only командой.
3. В течение 15 минут оператор явно выполняет `telegram_transition apply` с теми
   же bundle/digest и `--approved-plan PLAN_DIGEST`. Старый/чужой план не принимается.
   Миграция заново проверяет audit, отсутствие app sessions и состояние строк,
   делает отдельный backup и настоящий restore в изолированный PostgreSQL.
   Только после этого атомарно добавляет три таблицы и ограниченные grants.
   Restore использует уже имеющийся pinned image с `--pull=never`.
4. Проверяются защищённый backup, durable migration receipt, исходный audit prefix
   и preserved core rows. Новый код запускается с остановленным admission,
   выполняется штатный postcheck, записывается VERIFIED receipt новой версии.
   Telegram остаётся выключен. Автоматического запуска старых задач нет.

При потере ответа после apply **не повторять DDL**: `reconcile` сначала доказывает
отсутствие незавершённого maintenance container и проверяет копию/PG receipt.
После проверки разрешён только forward completion, не повтор apply.
Если commit не доказан, копия повреждена, audit/данные изменились или job ещё есть,
состояние остаётся pending; требуется разбор конкретной причины. Reboot/boot
pending release отвергается. Потеря последней записи журнала после VERIFIED
распознаётся без второго DDL.

`abort` возвращает старый код только **до DDL**, после проверки отсутствия всех
добавленных таблиц. Admission остаётся halted, abort журналируется. Повторный
stage после явного abort архивирует прежний журнал и требует свежий план.
После DDL generic rollback на старую схему блокируется. Нет drop tables,
restore поверх primary или обещания автоматического отката схемы.

## Полномочия migration operator

Это доверенная локальная операция владельца, не endpoint API и не AI tool.
Фиксированный одноразовый job использует проверенный broker image, PG admin
credential, private backup directory и (только для apply) control Docker socket.
Socket означает полномочия control user над его daemon; контейнер не делает
их безопасными для недоверенного кода. Никакие prompts/аргументы агента сюда
не передаются. У API, worker и Telegram process этого socket/admin key нет.
У job есть memory/CPU/PID/tmpfs/log limits, fixed actions и fixed database target.
При timeout оставшийся job не скрывается и блокирует повтор.

## Отдельное подключение настоящего бота

После проверки disabled release нужны подтверждённый Telegram owner ID,
bot credential и отдельное разрешение внешнего подключения.
`command_center.telegram_release --directory STATE/telegram --revision EXACT_SHA
--owner-id VERIFIED_OWNER_ID` принимает token только скрытым интерактивным вводом,
не через argv/чат/runner. При невозможности скрытого ввода отказывает.
Создаёт новые 0700/0600 bindings без перезаписи; нет API call и активации.
Печатает только connection digest и публичные ID. Неполный каталог после I/O
ошибки требует проверки, не автоматической перезаписи.

Затем prepare с `--telegram-connection-digest EXACT_DIGEST` включает явный scope
в новый bundle. После проверки и exact-bundle update запускается реальный клиент.
На этом шаге schema hash уже тот же, поэтому generic update подходит.
Само наличие токена не включает подключение. Проверка getMe должна подтвердить
bot ID; чужой webhook не удаляется автоматически.

Профиль фиксирован: app image с exact revision, только f1_app DB password,
private config/token directory, read-only rootfs, caps ALL dropped,
no-new-privileges, 128 MiB, .25 CPU, 32 PID, tmpfs 16 MiB, logs 2×1 MiB,
нет ports/socket/admin/API-owner/Redis credentials, restart=no.
API получает только публичный scope/digest, без token mount.
Остановка/отключение бота останавливает poller **предыдущего** bundle и проверяет
фактическое отсутствие running container; неподтверждённая остановка блокирует update.

Сеть telegram-access — обычный outbound bridge, **не** host/domain firewall.
Код клиента ограничен фиксированным HTTPS api.telegram.org и allowlist methods;
TLS/redirect/rate/retry guards сохраняются. Rootless не является VM isolation.

## Статус и мобильная панель

Heartbeat пишется только после успешного polling под PG leader lock, не чаще
раза в 15 секунд. Owner-only API проверяет audit chain, exact profile/digest/source,
текущий bot ID и DB time. Через 60 секунд без свежего события показывает stale.
Stop/error переопределяют старый heartbeat. HTTP mock никогда не отображается
как настоящий подключённый бот. Это свидетельство trusted process, не внешний
независимый мониторинг или доказательство production account security.
React обновляет раздел каждые 15 секунд, поддерживает narrow viewport и скрывает
данные при logout/error. Голос и AI-планирование остаются выключенными.

## Проверки и ограничения

Дополнительный `scripts/telegram_transition_smoke.py` выполняет сквозной переход
в настоящих старых/новых контейнерах, включая CLI maintenance job. Исходники
baseline восстанавливаются из Git objects точного 4cc6ec4 без remote credentials
и без дополнительного Git worktree. CI получает полную Git history для baseline.
Сценарий создаёт отдельный синтетический state, проверяет пароль и задачу старой
версии, stage/apply, потерю ответа после реального commit, reconcile без второго
DDL, новую задачу, serialized boot и сохранность данных. Runtime translation и
rootful backend находятся только в тестовом скрипте; production rootless gates
и logical bundle validation сохраняются. HTTP Telegram/AI/GitHub не вызывается.
Для двух наборов image layers нужно минимум 8 GiB свободного диска. Недостаток
ресурсов — отказ теста, не снижение production reserve или признание успеха.
Проверка не является настоящим reboot/systemd/rootless VPS trial.

Тесты используют настоящую отдельную legacy PostgreSQL и networkless restore,
но явную fake host orchestration в transition tests. Проверяются exact scope,
plan expiry, preserved data, повреждение backup, ambiguous commit, reconciliation
без второго DDL, abort до/после DDL, active job/stop guards и receipt custody.
Браузер проверяется Chromium на 320/390 px, не Safari на iPhone.
Synthetic heartbeat в UI-тесте не доказывает реальный Bot API.

Точечные scanner annotations: B108 относится только к Compose tmpfs string,
не к host tempfile; B106 — только к fixed file reference и пустому неиспользуемому
Redis field DB-only maintenance settings. Глобальные gates не отключались.
Первый локальный широкий прогон дал 114 passed / 11 failed из-за отсутствующего
Chromium и образов старого SHA. Эти результаты не считаются успешной приёмкой;
браузер установлен, финальные образы/прогон должны соответствовать одному SHA.
Предшествующие 97 targeted tests/32 infra не суммируются с полным suite.
Окончательные результаты и SHA фиксируются в PR/CI.

До будущего VPS trial не доказаны rootless cgroup/runtime этой новой версии,
полный host rollout/reboot/forward recovery и настоящий Telegram. Локальные
backups не являются offsite; RPO/RTO/MFA и production readiness не заявляются.
Нет real AI calls, CRM, paid resources, merge или live deployment в этой задаче.
