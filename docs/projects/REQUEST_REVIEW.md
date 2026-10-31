# Единая карточка подготовки запроса

Продолжение после PR #65: [ручной редактор плана](MANUAL_REQUEST_PLANS.md) добавляет
owner-only preview/save и schema 2 с декларативной привязкой к setup. Ниже описан
исходный read-only этап; утверждения про отсутствие writers и NOT_CHECKED всегда
относятся к нему и прежним schema 1 предложениям. Внешняя проверка/разрешение
по-прежнему не возникают.

После PR #64 карточка связывает сохранённый запрос, выбранный проект, текущий
setup и последнее предложение плана. В мобильной очереди раскрывается
«Подготовка запроса №N»; в private-owner Telegram доступна `/review N` со ссылками
из `/request` и `/requests`. Снимок показывает время, версии, проверки и один
следующий шаг: проект → настройки → план/уточнения → сверка scope и подключений.

## Значение статусов

Полный setup означает только заполнение пяти декларативных полей. CURRENT
плана означает совпадение с прежним PlanningContext. Он не включает setup:
изменение настроек не подтверждает соответствие старого плана новым данным.
Поэтому plan.setup_binding_verified=false и plan_setup_binding=NOT_CHECKED
всегда. У предложения не подтверждено происхождение от AI. Содержимое STALE
плана не возвращается; вопросы актуального предложения показываются отдельно.

Repository, verification и delivery остаются NOT_CHECKED, authorization —
NOT_GRANTED. OPEN/HALTED/RECOVERY описывают только Control. execution_ready,
execution_authorized, external_checks_performed, task_created, provider_called
всегда false, actions_enabled=[]. Карточка не создаёт план, задачу, grant,
approval, reserve или dispatch; обычный live planner не подключается.

## Чтение и безопасность

GET `/api/project-inbox/review?request_id=profile:number` требует прежнюю owner
identity/session/revocation, сохраняет no-store и безопасные validation/Denied
ответы. Read-only GET не требует CSRF. Один F1 Control lock охватывает audit,
intake anchor, assignment, plan и setup. Используются прежние readers, их
schema/source/size limits и повторный screen известных credentials. При ошибке
нет частичного результата или fallback к пустой «готовой» карточке.

Новых таблиц, writers, events или operation IDs нет. snapshot_digest связывает
наблюдение без observed_at, но не является capability или разрешением. Ответ
ограничен 65536 canonical JSON bytes. Успешный API read не меняет audit;
существующий отказ может записать request_denied. Доступа к VPS, репозиториям
проектов, provider config или ключам этот reader не получает.

Telegram N строгий и относится только к текущему private-owner profile.
Действуют прежние runtime/connection guards, durable query/receipt/delivery:
duplicate update возвращает прежний снимок, новая команда читает новые сведения.
Одно сообщение сокращает preview под 4096 characters / 8192 JSON bytes и ведёт
к полным `/request N`, `/plan N`, `/setup project-id`. Текст не исполняется как
HTML/команды; известные credentials снова проверяются перед Bot API.

Веб загружает карточку при раскрытии, без fan-out/polling. Обновление явное.
Несовпадение назначения со строкой очереди скрывает детали до reload очереди.
Timeout 10 секунд; close/logout отменяют запрос, поздний ответ не восстанавливает
данные. Некорректные ответы скрывают обзор, сохраняя рабочими очередь/назначение.
В карточке нет mutation controls.

## Доказательства и доставка

Real PG/API tests проверяют неизменность authority/ledger/inbox/audit на read,
общий F1 lock, смену project/setup/source/halt, stale/questions, роли, credential
rotation и integrity failures. Chromium 320/390 проверяет полный путь, XSS как
текст, malformed responses, смену проекта, retry, logout/abort и overflow.
Telegram tests проверяют profile/owner/group/forward, duplicates, Unicode limits
и screen очереди после смены credentials. Existing service smoke добавляет
`/review 1` после семи setup версий: 42 цикла /40 initial sends, batch limit 20,
старые coding repair/replay/mock PR и stop/resume assertions сохранены.

Это synthetic cloud proof. HEAD/merge-ref/CI фиксируются в Draft PR; на VPS
изменение не устанавливалось, проектов/AI не касалось. Frozen recovery/release
pairs сохранены; rootless/MFA/offsite/iPhone/live-provider acceptance не заявлен.
