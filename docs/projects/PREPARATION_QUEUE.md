# Очередь стадий подготовки

После ручных планов PR #66 сохранённый запрос может уже иметь план, хотя прежний
intake state всё ещё NEEDS_PLANNING. Новый обзор показывает следующий шаг из той
же логики, что индивидуальный `/review N`, без изменения admission state:

| Стадия | Что показывает |
| --- | --- |
| select_project | Требуется выбрать проект |
| complete_setup | Выбран проект, но черновик настроек неполный |
| prepare_plan | Настройки заполнены, плана ещё нет |
| refresh_plan | Последний план устарел |
| answer_questions | В актуальном плане остались вопросы |
| verify_scope | Требуется сверить задачу и внешние подключения |

Полнота настроек проверяется раньше состояния плана. Последняя стадия означает
следующий шаг подготовки, не готовность запуска или проверенный доступ к проекту.
Модели, repository/verification/delivery/authorization checks не вызываются;
execution_ready/execution_authorized/provider_called/external_checks_performed/
task_created=false и actions_enabled=[]. Новых таблиц, событий или writers нет.

## Мобильная панель

В разделе проектов раскройте «Стадии подготовки запросов». Обзор загружается
одним GET после раскрытия, без polling/fan-out. Фильтры выбирают проект и стадию;
счётчики стадий относятся к выбранному проекту до stage filter. Видны номер,
следующий шаг, версии настроек/плана и исходный текст. Карточка подготовки с тем
же редактором открывается прямо здесь, включая запросы старше первых 50 прежней
очереди. Запись из редактора обновляет checkpoint и обзор стадий.

Страница содержит до 10 запросов; всего допускается 1000 pending requests.
Порядок — created_at DESC, id DESC, включая равные timestamps. Первая страница
возвращает snapshot_digest, следующие передают его в GET. Если состав, текст,
assignment/setup/plan/context или фильтры изменились, переход отвергается без
частичного результата. «Обновить стадии подготовки» читает первую страницу
заново. Digest — привязка чтения, не capability или разрешение. Logout/закрытие/
смена фильтров отменяют запросы; поздний ответ отбрасывается. Ошибка обзора не
скрывает остальную панель. Текст остаётся React text, все входные ответы строго
проверяются. Повторно открытые редакторы одного запроса имеют разные HTML IDs.

GET `/api/project-inbox/preparation` принимает project, stage, page (1–100) и
необязательный snapshot (64 lowercase hex). Owner identity/session/revocation,
no-store и безопасные validation/Denied ответы прежние. Read-only GET не требует
CSRF. Ошибка может попасть в существующий request_denied audit; успешное чтение
не меняет protected audit, inbox, Control, tasks, grants или ledger.

## Telegram

Private-owner `/queue` показывает до 5 запросов, счётчики, ссылки `/review N` и
фильтры. Примеры: `/queue lnauto`, `/queue all answer_questions`,
`/queue lnauto verify_scope 2`. Номер страницы 1–200. Бот даёт команды перехода
и фильтров; вручную копировать hashes не требуется. Каждая новая команда читает
свежий снимок, поэтому позиции могут сдвинуться — это явно указано в ответе.
Duplicate update сохраняет прежний durable ответ; новая команда видит изменения.

Счётчики и запросы относятся только к текущему Telegram profile. Прежние
owner/private/source/runtime/connection/delivery guards сохранены. Страница,
которой больше нет, ведёт к `/queue`; неизвестные параметры не превращаются в
обычный запрос. Preview сокращается под 4096 characters /8192 canonical JSON
bytes, входной текст экрануется отдельно под прежние 2000 bytes. Полный ответ
снова проверяется на известные credentials; транспорт и queued delivery сохраняют
свои guards. Непроверенные inputs не интерпретируются как команды/HTML.

## Согласованность и стоимость чтения

Один F1 Control transaction включает check_audit, pending rows и earliest owner
receive anchors, assignment history, replay setup history и plan records.
Ограниченные bulk SELECT загружают историю один раз. Общие intake/context/plan
validators используются индивидуальными readers и batch path; отдельного
источника полномочий или упрощённого fallback нет. Setup views кэшируются только
внутри этого снимка. Проверки source binding, canonical/digest/sequence, historical
setup references, stale content и текущих известных credentials сохраняются.

Все подходящие pending rows валидируются до project/stage filter и пагинации.
Повреждённые или sensitive данные не дают пустой/частичной «готовой» очереди.
Ограничения существующей истории setup/plan/assignment не расширены. Ответ API
ограничен 65536 canonical bytes, поэтому патологический escaped text может
дать безопасный отказ, а не обрезанный текст. Проверка SQL count сравнивает один
и 23 запроса: число SELECT не растёт (не более 12). Это не обещание конкретной
сетевой задержки или benchmark действующего VPS.

## Доказательства и доставка

Real PG/API тесты сверяют все стадии с индивидуальными карточками, стабильную
пагинацию/равные timestamps, контекстные изменения, source, roles, corrupted
history, credential rotation, capacity/response limits и Control lock. Telegram
проверяет фильтры, страницы, private/profile boundaries, duplicates и повторный
screen очереди. Chromium 320/390 покрывает lazy read, stage filtering, edit
readback, старые запросы, snapshot conflict/restart, malformed response, logout,
разные IDs двух редакторов, touch targets и overflow.

Существующий container service smoke расширен до 51 cycles /49 initial sends /
36 read-only queries: `/queue`, filter с найденным и пустым результатом. Прежние
coding repair/replay/mock PR, семь setup версий, две ручные версии и stop/resume
assertions сохранены. Образы финального CI собираются из его точного source SHA;
старые локальные образы не переименовываются ради PASS.

На VPS изменение не устанавливалось, реальных Bot API/AI/project probes и расходов
не было. Frozen recovery runtime bf91c05c754ad41e7f89223ec8d05c02c9007de1, release
pairs и отдельная host reconciliation/approval остаются прежними. Rootful cloud
proof не доказывает rootless/MFA/offsite/iPhone/live-provider acceptance.
