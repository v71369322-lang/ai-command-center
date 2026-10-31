# Текущий контекст и облачный handoff

Продолжение **31 октября 2026, после PR #65**: [ручные планы запроса](projects/MANUAL_REQUEST_PLANS.md)
добавляют редактирование цели, шагов, критериев и вопросов в мобильной карточке
и private-owner Telegram. Это owner-authored schema 2 в прежнем audit journal:
общие версии с прежними планами, exact request/assignment/setup/source binding,
preview/save и защита от stale/повторной записи. Изменение настроек делает такой
план STALE; DECLARED_MATCH означает только совпадение сохранённых деклараций.
AI, задача, grant и расходы не возникают. Generic API timeline теперь скрывает
содержимое обоих типов плана для всех ролей. Новых таблиц/migrations нет;
legacy schema 1 читается с прежним неподтверждённым происхождением.
PR #65 проверен заново: HEAD 33d10d4, full CI SUCCESS — 1492 Python /1 прежнее
предупреждение и 962 infrastructure, все container smokes. HEAD/merge-ref/CI
нового этапа фиксируются в отдельном Draft PR поверх #65. VPS/проекты/расходы
не менялись; frozen recovery/release pairs и отдельная host acceptance сохранены.

Продолжение **30 октября 2026, после PR #64**: [единая карточка запроса](projects/REQUEST_REVIEW.md)
соединяет owner request, назначение, setup и предложение плана в одном checked
PG snapshot. Мобильная очередь и `/review N` показывают версии, блокеры и следующий
шаг. План не получает подтверждённой связи с setup; execution/provider/probe flags
остаются false. Новых writers/таблиц/authority нет. VPS/проекты/расходы не менялись;
recovery/release pins сохранены. PR #64 подтверждён: HEAD 63b6eb6, full CI SUCCESS
1434 Python /1 warning и 962 infrastructure, все container smokes. Финальная
проверка нового этапа — в отдельном Draft PR поверх этой базы.

Крупный cloud-этап **30 октября 2026, после PR #63**: владелец попросил большой
рывок вместо отдельных маленьких доработок. [Единый процесс подготовки проекта](projects/SETUP_WORKBENCH.md)
объединяет сводку, редактируемый draft, preview/save, историю/restore и запись
из Telegram в одном PG/audit workflow. Версии и idempotency общие для web/API/
Telegram; ошибочная/устаревшая запись не затирает новую. Полнота draft не является
проверкой подключения, все execution/probe flags остаются false. Новые события
скрыты из общей API timeline; подробности только owner setup readers.
VPS/реальные проекты/расходы не менялись, release/build/recovery pins сохранены.
Итоговые HEAD/CI этой единой доработки — в отдельном Draft PR, не host acceptance.

Продолжение **30 октября 2026, после PR #62**: владелец без компьютера просит
продолжить. [Telegram-план подключения](telegram/PROJECT_CONNECTION_PLAN.md)
добавляет `/connection project-id`, guide без аргумента и навигацию из
`/projects`/help. Используется тот же PLAN_ONLY каталог и прежний durable
Telegram query/delivery путь; доступы проектов, AI, серверы и grants не
активируются. Новая команда на VPS не устанавливалась. Recovery pins/build и
release pairs сохранены; итоговые HEAD/CI фиксируются в отдельном Draft PR.

Продолжение **30 октября 2026, после PR #61**: владелец остаётся без компьютера
и попросил двигаться дальше после объяснения подключений проектов.
[План подключения](projects/CONNECTION_PLAN.md) добавляет owner-only GET и
раскрываемые пункты в панели: ожидаемый репозиторий, среда проверки, доставка.
Все три статуса NOT_CHECKED; это PLAN_ONLY без сетевых проверок, credentials,
подключения проектов, задач и расходов. Реальный recovery/apply остаётся первым
host-этапом после доступа; его pins/build/release pairs не меняются. Итоговые
HEAD/CI новой ветки проверяются в отдельном Draft PR.

Продолжение **30 октября 2026, после PR #60**:
[один локальный offline-запуск](infrastructure/FIRST_RECOVERY_OFFLINE_SESSION.md)
связывает проверенный существующий broker, protected inspection и disabled draft.
Он снимает ручное копирование hashes/JSON; старые source/runtime/release pins
сохраняются. Сам запуск на VPS не выполнялся, новых расходов или tokens нет.
PR #60 проверен заново: HEAD7fb08e7, full CI1318 Python /1 прежнее предупреждение
и923 infrastructure SUCCESS; offline923 повторяет тот же набор.

Следующий облачный шаг **30 октября 2026**:
[автоматическая подготовка отключённого recovery-профиля](infrastructure/FIRST_RECOVERY_DISABLED_PROFILE.md).
Из защищённого исходного config и свежего локального отчёта создаётся только
новый private draft с mode=disabled, снятыми operator/tariff confirmations,
пустыми evidence/budget evidence и неподтверждённым балансом. Один вызов,
суммарный финансовый предел и original parent digest сохраняются; runtime,
release pairs и build-only пакет не меняются. Реальный host draft здесь не
создавался. Предыдущий PR #59 проверен заново: HEAD2f758aa, full CI1317 Python
/1 прежнее предупреждение и872 infra SUCCESS; offline872 — тот же набор.

Продолжение **30 октября 2026, после PR #58**: владелец снова без компьютера и
попросил продолжить облачную подготовку. [Один read-only recovery отчёт](infrastructure/FIRST_RECOVERY_READ_ONLY_INSPECTION.md)
объединяет PG/SQLite/локальный Docker/profile expiry перед следующим owner SSH
заходом. Это operator-only дополнение; runtime bf91c05, старые release pairs и
сборочный пакет сохранены. PR #58 проверен заново: HEAD cf05dd1, full CI SUCCESS
1313 Python /1 прежнее предупреждение и850 infrastructure; offline CI повторяет
тот же набор850, а не добавляется к нему. Новый reader на VPS не запускался;
host build/update/token/paid approvals не считаются продлёнными из cloud-просьбы.

Следующий cloud-этап, **30 октября 2026**: владелец отдельно разрешил разработку
[одноразового восстановления](f2-2/ONE_CALL_RECOVERY.md). Новый профиль/задача
ограничены одним вызовом и 34.7868 ₽; исходные FAILED/grant/расход сохраняются.
Parent проверяется по прежнему audit/ledger, суммарный лимит не расширяется.
Prepare и запрос новой Telegram-карточки не являются paid consent. Старый
first-pilot grant остаётся одноразовым. Новый source/CI/operator transition и
отдельные host/paid approvals нужны до реального запуска; VPS 322186d пока
не получает эту реализацию автоматически.

Актуализация **30 октября 2026, после 10:48 UTC**:
[первый реальный OpenAI-вызов и остановка по контракту исходника](f2-2/SOURCE_SCHEMA_FAILURE_2026-10-30.md).
Владелец применил runtime322186d/bundleac6462b…094d и подтвердил новую версию в
Telegram. Задача938e838d… после отдельного paid consent завершилась FAILED:
одна COMPLETE OpenAI-операция, расход шлюза0.047840625₽, спорный резерв0;
публикации PR в предоставленном списке операций нет. Сохранённый ответ отклонён
как synthetic_language_scope_violation: модель вернула цикл, тогда как фиксированный
пилот разрешает две AST-формы. Cloud correction ограничивает JSON Schema этими
вариантами; verifier/F1/финансовые guards сохраняются. Это ещё не исправление
действующего VPS и не разрешение повторить платную задачу. Старые записи ниже
сохраняют историческое происхождение и не заменяют этот более поздний результат.

Снимок на **28 октября 2026, 14:03 UTC**. Это контекст продолжения, не новое
разрешение доступа, расходов, merge или deployment. Перед работой сверять
актуальные HEAD/PR/CI; ниже указаны проверенные точки, не вечные значения.

Последующее дополнение 28 октября: [фактическая cloud-проверка проектов](projects/CLOUD_VALIDATION_2026-10-28.md).
LNAuto прошёл native Linux baseline (13 backend с PG / 28 frontend / 10 browser),
без изменения исходников. Ваниль: свежий Prisma checksum GET снова дал HTTP 403;
её полный C2 runtime остаётся BLOCKED. Ниже сохранён исходный metadata snapshot.

Дополнение **28 октября, 16:43 UTC**:
[Capital-Lab проверен в текущей cloud-сессии](projects/CAPITAL_LAB_CLOUD_CHECK_2026-10-28.md):
1414 backend passed / 13 skipped / 1 warning, 138 frontend passed,
настоящие HTTP/PG и build PASS, исходники не менялись.
LNAuto затем получил отдельный [Draft UI PR #1](https://github.com/v71369322-lang/LNAuto/pull/1),
`6eb27e105f976130b9a7975517fc90504bdb1f9f`, с успешным frontend CI;
код этого UI-пилота уже отличается от первоначального read-only снимка ниже.
LNAuto на VPS не развёртывался. Название CryptoLab пока не сопоставлено с
отдельным доступным repo; Capital-Lab не переименован. Ни один из этих результатов
не подтверждает действующий канал F33 или доставку новой версии Commander на VPS.

Следующая cloud-доработка: [главное меню Telegram](telegram/OWNER_MENU.md),
source/test checkpoint `974430a260cde68d4e75f50cfd73e2cee886bede`.
Четыре кнопки вызывают прежние readonly-команды; AI/расходы/CRM не включаются.
Локально 140 targeted / 105 infrastructure, Ruff/OpenAPI/TypeScript/Vite PASS.
Итоговые HEAD/полный CI этой отдельной ветки сверять в её Draft PR.
На VPS меню пока не доставлено; F33 по-прежнему требует reconciliation.

Следующая доработка поверх меню: [кнопки выбора проекта запроса](telegram/PROJECT_PICKER.md),
checkpoint `bbd4d08092a214ada2fd284b4905101b2085d18b`.
Локально 203 targeted / 105 infrastructure PASS; назначение остаётся метаданными,
source/version/delivery/audit checks сохраняются. Итоговый полный CI — в Draft PR
этой отдельной ветки. Это также ещё не обновление действующего бота/VPS.

Более позднее подтверждение **28 октября, вечер МСК**:
[реальный канал F33 проверен](https://github.com/v71369322-lang/ai-command-center/blob/c4aa5a8449ba1e9a57d3922160bae3ffb33ced70/docs/infrastructure/F33_LIVE_VALIDATION_2026-10-28.md).
Владелец установил службы через SSH; cloud GitHub job на brain1 вернул signed
SUCCEEDED, exact replay идентичен, неразрешённый пакет отклонён подписанным
bundle_not_approved. Ed25519 проверен в облаке. Профиль истекает **22:24:55 МСК**,
max_updates=0, сам не продлевается и не останавливает runner по expiry.
Это уточняет исторические unknown ниже; Telegram app остаётся на 316dc16.

Следующий отдельный этап — [F34: подготовка Telegram update](infrastructure/F34_TELEGRAM_UPDATE_PREPARATION.md).
Target application SHA b2e71fe. Новые operator tools готовят private staged
binding и требуют отдельного exact approval для apply.

Актуализация **29 октября, МСК**: [F34 применён владельцем на VPS](infrastructure/F34_LIVE_VALIDATION_2026-10-28.md).
Application b2e71fe, operator tools 364c5eb, live bundle a1cf9b0d…be9c8,
activation VERIFIED и F34_UPDATE_VERIFIED. Проверены Telegram capture/project
choice/readback нового №131179132 и старого №131179125; /coding_plan доступен.
Это owner-provided SSH logs + desktop Telegram Web, не прямой cloud host probe.
Новые запуски остаются остановлены; post-update coding cycle и iPhone acceptance
пока не выполнены. AI/CRM/paid APIs/public HTTPS не подключены. Исторические
описания прежнего VPS состояния ниже не заменяют этот более поздний результат.

Следующая ограниченная cloud-доработка — [снятие обычной остановки через Telegram](telegram/NORMAL_STOP_RESUME.md):
двухшаговый /resume и одноразовая owner button используют прежний F1 resume;
recovery/security/неопределённые исполнения остаются блокерами. Новая версия
на VPS не доставляется автоматически; текущая live b2e71fe этой команды не имеет.

Cloud continuation: [пакет доставки Telegram resume](infrastructure/TELEGRAM_RESUME_RELEASE.md)
закрепляет target bdc8cbc (PR #37, full CI SUCCESS:694 Python /1 warning,
отдельно143 infrastructure). Operator helper получает явно выбранный fixed
profile b2e71fe→bdc8cbc; старый default f34 сохранён. Prepare-only script требует
нового разрешения/точного operator SHA и создаёт отдельный кандидат, не update.
На VPS ничего не выполнено, нового host bundle digest пока нет. Владельцу вне
компьютера не требуется вводить команды или передавать credentials.

Следующий отдельный cloud-шаг — [сводка готовности в Telegram](telegram/READINESS_SUMMARY.md)
поверх PR #38. `/readiness` читает F1 control, очередь этого подключения и, если
доступен, локальный профиль первого эксперимента; отсутствие gateway config
честно остаётся unknown. Не выдаёт grants и не читает ключи, не меняет спорные
резервы. Локально126 targeted passed; полный итоговый CI — в отдельном Draft PR.
На текущем VPS b2e71fe этой команды нет. PR #38 по-прежнему доставляет только bdc8cbc;
новую функцию нельзя считать включённой в прежний закреплённый пакет.

Продолжение в облаке: [единый mobile-релиз Telegram](infrastructure/TELEGRAM_MOBILE_RELEASE.md)
позволяет подготовить один переход b2e71fe→d932baa с `/resume` и `/readiness`.
Application [PR #39](https://github.com/v71369322-lang/ai-command-center/pull/39)
имеет успешный CI:724 Python /1 warning, отдельно210 infrastructure. Новый
operator profile `telegram-mobile` явно выбирается; прежние default/profiles
сохранены. Локально280 infrastructure passed. Source archive/manifest — только
ignored cloud evidence; host candidate/image IDs пока отсутствуют. VPS не менялся,
старые approvals не продлевались. Финальный operator HEAD/CI — в отдельном Draft PR.

Следующий cloud-шаг: [офлайн preflight первого AI-эксперимента](f2-2/OFFLINE_PREFLIGHT.md)
проверяет локальный профиль без HTTP clients, Gateway/Store и чтения credential
files. Даже LOCAL_CHECKS_PASSED не подтверждает remote state или paid consent.
Закоммичен только disabled template; реальный запуск CLI дал ожидаемый BLOCKED,
0 external calls. Локально58 новых /338 infrastructure, отдельно16 существующих
pure F2.2 tests; поднаборы не складываются. Src/runtime/пакет PR #40 остаются
неизменными. Account/model/funding/GitHub App/repo/credential/ledger проверки и
окончательное разрешение живого эксперимента остаются отдельными gates.

## Command Center: исходники и проверки

Новая фактическая диагностика: [GitHub App capability, 30 октября](infrastructure/GITHUB_APP_CAPABILITY_2026-10-30.md).
Owner собрал2822320 на двух rootless daemons, не применял. UI OpenAI подтвердил
Responses/write, List models/read, баланс$8, auto-reload OFF. Вторая token attempt
выдала и сохранила candidate, но strict repository guard отказал только на
push:true. Отдельный readonly Git discovery дал200; expiry09:41:31UTC/12:41:31МСК.
Новый код добавляет scoped bounded GET/полный parser при false/absent push,
сохраняя identity/main/admin/F1 checks и старый strict default. Это ещё cloud
исправление; NO_RETRY/отсутствие final token и actual VPS d932baaf сохраняются.
Нужен новый source package; старые10 pins не переназначаются. Final CI — в Draft PR.
Новый11-й named transition first-experiment-github-capability: d932baaf→322186d;
runtime checkpoint322186d, последующие изменения только operator/tests/docs.

Следующее cloud-продолжение: [закрытый F1 planning gateway](planning/F1_HTTP_MOCK_GATEWAY.md).
Owner-only waiting task, отдельный узкий ExternalGrant и прежние F1 Approval/
lease/fence/source/financial ledger дают один точный HTTP-mock planning request.
Draft и task result атомарны; cached COMPLETE не отправляется повторно, unknown
outcome/context change не позволяют новый вызов. Coding/first-pilot scopes не
переносятся на planning. Generic APIs и production broker отвергают неподдержанный
путь; live mode/keys/env/UI/runtime пока отсутствуют. Все10 release pins/VPS прежние.
Финальный локальный scope338PG/mock passed /5execution deselected включает52
новых cases; core67passed пересекается с ним. Итоговые HEAD/CI — в отдельном Draft PR.

Следующее cloud-продолжение: [сохранение и Telegram-просмотр черновиков](planning/DRAFT_STORAGE_AND_TELEGRAM.md).
Внутренний owner import повторяет общий locked review и сохраняет bounded
unverified advisory document в прежний audit, без task/grants/расходов. Версии
и identity обеспечивают concurrent dedup и recovery; `/plan номер` и закреплённые
страницы показывают только current context. Stale body скрыт; источник явно
не подтверждён, исполнения нет. Локально314PG/mock passed,56новых cases включены.
Источник реальных AI-планов пока не подключён. Фактический VPS и все10 release
pins остаются прежними; новая команда требует будущего отдельного source package.
Итоговый HEAD/CI — в отдельном Draft PR.

Следующий независимый cloud-шаг: [офлайн-контракт обычного AI-плана](planning/SAVED_REQUEST_CONTRACT.md).
Owner snapshot связывает saved request/project version/intake+current source/control;
Responses formatter и строгий parser проверяют advisory proposal без HTTP clients,
provider keys, задач или grants. Read-only review сверяет актуальный PG context;
model fields/usage не являются provider/billing evidence. Локально198PG/mock passed,
61новых cases включены в198. Финальный HEAD/CI — в отдельном Draft PR.
Новых Telegram/API команд и подключения обычного AI-планирования пока нет.
Десять существующих release targets и прежний first-experiment scope не меняются.

Следующая cloud-доработка: [явное платное разрешение из Telegram](telegram/EXPERIMENT_AUTHORIZATION.md).
`/authorize_experiment` показывает точные условия; только отдельная observed
private-owner кнопка использует прежний F1 authorize/approve с финансовым scope.
Запрос карточки/prepare/resume не разрешают оплату. Task/source/profile/epoch/
delivery/expiry и девять gates проверяются повторно под Control lock; grant и
reply атомарны, повтор/lost acknowledgement не создают новый запуск. Локально
654PG/mock passed /9 execution deselected; поздний targeted84passed /3deselected
включает65 новых cases и пересекается с654. Итоговые SHA/CI — в Draft PR.
Новая команда ещё не доставлена на VPS; реальных provider calls не было.
Runtime checkpoint2822320; отдельный десятый profile first-experiment-authorize
закрепляет один переход d932baaf→2822320. Прежние девять source pairs/default f34
сохранены; integration/readiness binding и новый exact host build остаются обязательны.

Следующий шаг к первому AI-запуску: [подготовка фиксированной задачи из Telegram](telegram/EXPERIMENT_PREPARATION.md).
`/prepare_experiment` использует общий с API owner-only creator и единственный
request key. Новая задача WAITING_APPROVAL, без grants/расходов/executor outbox;
повтор возвращает ту же задачу. Ordinary saved requests остаются NEEDS_PLANNING.
Receipt/source/epoch/120sec/immutable-task guards и atomic reply composition
сохраняются. VPS пока недоступен из текущей cloud-среды; финальное подключение
и первый paid вызов не объявляются выполненными. Source/operator/CI — в Draft PR.
Runtime checkpoint7467df2; девятый profile first-experiment-prepare закрепляет
один переход d932baaf→7467df2 с предыдущими функциями и latency fix. Восемь
прежних targets/default f34 сохранены; rootless host build/stage/apply ещё нужны.

Следующая cloud-доработка: [Telegram response latency](telegram/RESPONSE_LATENCY.md).
Известный NEW ответ текущего profile переводит getUpdates в timeout0; idle default
уменьшен10→2секунды. Inbound controls остаются перед sends, batch/delivery bounds
и uncertain-send guards прежние. Это не замер VPS и не ускорение самой AI-генерации.
Новые exact-source images/пакет потребуются для доставки этой доработки; уже
собранный application a5d867c и восемь release targets не меняются.
Итоговые tests/source/CI фиксируются в отдельном Draft PR.

Cloud checkpoint **30 октября, после отъезда владельца**:
[единый порядок продолжения первого AI-запуска](f2-2/LAUNCH_CHECKPOINT.md)
связывает сохранённые credentials/build с оставшимися financial/config/deployment/
paid gates. Owner offline inspect/новый plan operator8e60568 получены; результат
предложенной второй выдачи неизвестен. При возвращении сначала read-only сверка
обеих попыток, expiry и deployment, без повторного prepare. Длительные prerequisites
готовятся до нового часового token. В облаке изменяется только документация;
VPS/credentials/paid calls не затрагиваются, повтор всей установки не требуется.

Актуализация30октября2026: владелец подтвердил прежний live d932baaf и private
custody ключей; offline plan operator0476b4c получен, application a5d867c локально
собран без deployment. Одна выдача GitHub token вернула BLOCKED: receipt
03:09UTC содержит token_request_attempted=true, expires_at04:06:33UTC, но
token file отсутствует и точный post-response stage/error не сохранён.
Это owner evidence, не cloud host probe. Не повторять исходную попытку/не
удалять её журнал. [Разбор и исправление диагностики/candidate custody](infrastructure/FIRST_EXPERIMENT_GITHUB_TOKEN.md)
идут отдельным cloud PR поверх #47; runtime guard/release targets остаются прежними.
Новая выдача не выполнена, paid_calls=0; дополнительные credentials требуют
нового reviewed owner решения, а не повторного использования прежнего плана.

Следующее cloud-продолжение поверх PR #46 — [операторская подготовка GitHub token](infrastructure/FIRST_EXPERIMENT_GITHUB_TOKEN.md).
Offline plan связывает source/key identity/paths с одной scoped credential
операцией. Future prepare после owner approval выпускает токен только для
ID1438229730, проверяет его effective repository count/permissions/baseline и
сохраняет private0600 без подключения runtime. Unknown outcomes не повторяются.
Полное число repos установки не выводится из scoped token; отдельный false
сохраняется. Реальные credentials/API/VPS пока не использованы; app target и
release pins PR #46 не меняются. Итоговый operator SHA/CI — в отдельном Draft PR.

Следующее cloud-продолжение поверх PR #45 — [отмена первого эксперимента](telegram/EXPERIMENT_CANCELLATION.md):
`/cancel_experiment` вызывает прежний F1 cancel для UUID, закреплённого при
получении команды. Повтор/перезапуск не отменяют будущую или заменённую задачу.
Расходы, спорные резервы и запрет повторного provider вызова сохраняются;
CANCEL_REQUESTED не выдаётся за подтверждённую остановку. VPS не менялся.
Итоговые source/operator pins и clean-source CI — в отдельном Draft PR.

Следующее cloud-продолжение поверх PR #44 — [явные уведомления эксперимента](telegram/EXPERIMENT_NOTIFICATIONS.md):
owner `/watch_experiment` / `/unwatch_experiment`, consent в прежнем audit и
delivery через существующий collector/outbox, без новой task authority. По
умолчанию выключено; source/profile/task binding, semantic dedupe и no-resend
для неизвестных отправок сохраняются. Source/image/deployment требуют нового
закреплённого пакета, paid calls этим не разрешаются.

Следующее cloud-продолжение поверх PR #43 — [просмотр первого AI-эксперимента](telegram/FIRST_EXPERIMENT_STATUS.md).
`/experiment` читает одну фиксированную API-задачу и проверенные локальные
result/financial anchors без Gateway/HTTP client construction и ключей.
Сохранены строгая Telegram scope для обычных тестов, paid approval и F1 guards.
Уточнён status после billing settlement: SETTLED сохраняет неопределённость
результата и запрет повтора. Финальные source/PR/CI — в отдельной ветке;
на VPS ничего не применяется автоматически.

Следующий cloud-шаг после owner account setup —
[явный deployment profile первого AI-эксперимента](f2-2/DEPLOYMENT_PROFILE.md).
Прежний VPS profile отвергал F2 env/mounts/egress, поэтому сохранённые и проверенные
owner credentials ещё не означали подключение runtime. Новый opt-in binding
закрепляет config bytes и прежний profile hash, предоставляет config API/broker,
а keys/egress только broker. Default closed и F1/финансовые guards сохраняются.
Source/image build, новые host bundle/approvals и paid run этим не выполняются.
Владелец подтвердил model metadata HTTP200 и App5524444/installation176497504
identity/permissions/target binding; selected count, installation token, payment
upper bound и новый actual runtime profile остаются отдельными проверками.
Итоговые commit/PR/CI этого изменения сверять в его отдельной ветке.

Продолжение без owner SSH: [закреплённый AI-профиль в Telegram readiness](telegram/READINESS_SUMMARY.md).
Явный prepare flag добавляет readonly config в Telegram без ключей и новых сетей;
прежние bundles сохраняются. `/readiness` использует существующие локальные gates,
не выполняет удалённые проверки и не выдаёт grants. Новый application SHA требует
своего закреплённого пакета; target PR #42 не изменяется автоматически.

- Репозиторий: [v71369322-lang/ai-command-center](https://github.com/v71369322-lang/ai-command-center).
- Предшествующая реализация до этапа меню: [Draft PR #31](https://github.com/v71369322-lang/ai-command-center/pull/31),
  `feat/telegram-coding-demo`, `b2b57ba8ae52d8ae7629c13647f250d0d92cfae7`.
- [CI этого SHA](https://github.com/v71369322-lang/ai-command-center/actions/runs/40698783681):
  593 Python passed / 1 Starlette-httpx warning, отдельно 105 infrastructure passed.
  Проверен merge-ref `a0d24fcb794c809d97c590775e9d4dfe92c4e4fa` с базой PR #30.
  Последующий documentation-only PR имеет собственный HEAD/CI в GitHub.
- Базы: #31 → #30 (`4b2acb0462f217b599790989f1b9785b15d4cbfe`) →
  #29 (`b7a32cde4852ad030b3464420bfe12497edc8709`) → #28 и предшественники.
  Исправленный deployment #17 (`53565cc2ca232fb2cf6d6552a3ae04b462d92956`)
  является предком проверенной реализации. Эти PR не объединены в main.

Реальные Git-изменения, tests/repair, отдельный verifier, durable F1 очередь,
restart/recovery/watchdog/backup и Telegram service проверены в облаке.
AI/provider и PR в coding-сценарии — mock. Настоящие OpenAI/GitHub adapters
остаются отдельно разрешаемыми и по умолчанию закрытыми. Полная production
готовность и приёмка реальных CRM не подтверждены.

Навигация:

- [F1 runbook](f1/README.md), [F2](f2/IMPLEMENTATION.md),
  [F2.1 readiness](f2-1/READINESS.md), [первый AI-эксперимент](f2-2/EXPERIMENT_PLAN.md).
- [Очереди проектов в Telegram](telegram/PROJECT_QUEUE.md),
  [mock coding-команда](telegram/CODING_DEMO.md).
- [Ограниченный серверный канал](infrastructure/BOUNDED_OPERATIONS_CHANNEL.md),
  [возобновление F33](infrastructure/F33_RESUME_FROM_PHONE.md).
- Первоначальный облачный план сохранён отдельно в
  [PR #18, exact source](https://github.com/v71369322-lang/ai-command-center/blob/d757b0bd2d121d0868173267c7dfc8b00f299eb5/CLOUD-MIGRATION-PLAN.md).
  Он не потерян, но его исторические статусы не заменяют этот снимок.

## Что известно о VPS, а что не проверено сейчас

Первоначальная cloud-разработка не подключалась к VPS. Впоследствии владелец
выполнил F33 bootstrap через собственный SSH и разрешил временную диагностику;
настоящие GitHub runner jobs и подписанные ответы проверены в облаке (ссылка выше).
Прямого Cloud SSH не было. Ниже сохранены происхождение и ограничения результата.

Приложение на 176.12.75.135 было обновлено до
`316dc1615dea224bcf4bd595d87048d19820bd21`, Telegram live bundle
`0ee8a6023296fdacfe632c2f364c488b2564db399bfd15af357812e41004d64b`.
Владелец проверил реальное сохранение/чтение запроса и уведомление о
синтетическом тесте, в том числе с iPhone. Cloud PR #27–#31 этим автоматически
не доставлены. Парольный вход через SSH tunnel не равен публичному HTTPS/MFA.

На VPS подтверждены acc-control UID 1000 и acc-exec UID 1001, отдельные rootless
Docker. После возвращения владелец подтвердил отсутствие трёх enrollment paths,
неизменность live bundle, hash старого bootstrap и отсутствие регистрации runner.
По новому явному разрешению diagnostic profile установлен, зарегистрирован и
запущен. Три настоящих mailbox job проверили status/replay/denial; приложение
не обновлялось. Это не бессрочный доступ и не разрешение source build/update.
Не повторять bootstrap и не заменять policy/key/journal после expiry. Новая
точная операция требует собственного разрешения; CRM 206.223.246.79 не затрагивать.

## Три бизнес-проекта: проверен только GitHub-контекст

В исходном снимке проверены метаданные GitHub: доступность, private visibility, branches/refs,
открытые PR и Actions runs по известным точным SHA. Исходники, клиентские
данные, локальные Windows-копии и полнота переноса в первоначальном metadata-снимке не читались,
не сравнивались и не изменялись. Последующая отдельная read-only проверка
LNAuto и C2-блокера Ванили описана по ссылке выше; бизнес-данные и Windows-копии
по-прежнему не читались. GitHub-доступ Codex не означает подключение
этих репозиториев к runtime coding-agent Command Center.

| Проект | Private repository / ID | Снимок main | Отдельная работа в GitHub |
| --- | --- | --- | --- |
| Ваниль и Сахар | [Vanilla-Sugar-CRM](https://github.com/v71369322-lang/Vanilla-Sugar-CRM), `1435253397` | `6b4c79b6955d75ad33f97569cad47884248d5bbf` | [Draft PR #1](https://github.com/v71369322-lang/Vanilla-Sugar-CRM/pull/1), `cloud/c2-linux-runtime`, HEAD `6b0ca0d4d03d26aec4d6e7511b30e42ff63b8df8`, база main |
| LNAuto | [LNAuto](https://github.com/v71369322-lang/LNAuto), `1434161534` | `a339242387cd5729f252613d6a3d17cbafe00007` | В снимке только main, открытых PR нет |
| Capital Lab | [Capital-Lab](https://github.com/v71369322-lang/Capital-Lab), `1434576176` | `1b18e033e127b853fd95e32cab88053e719bfdab` | [Draft PR #1](https://github.com/v71369322-lang/Capital-Lab/pull/1), `codex/cloud-c2-linux-compatibility`, HEAD `0e1a16986baa5a217b2ec03d0db5146c51bb6f8a`, база main |

Actions API с фильтром exact head_sha вернул **0 runs** для всех трёх main SHA
и двух перечисленных PR HEAD. Это **не PASS**, не доказательство отсутствия
локальных проверок и не утверждение, что workflow-файлов нет. Build/tests,
санитизация всей истории и полнота импорта пока не подтверждены этим снимком.
Упомянутые PR только прочитаны как metadata: их diff не ревьюился и merge
не рекомендуется без отдельной проверки. Default main не назначен автоматически
рабочей базой поверх открытых migration PR.

## Как ускорять параллельную работу

1. До подтверждения облачной базы не редактировать параллельно исходную
   Windows-копию: иначе появятся две расходящиеся линии. Не удалять её — она
   остаётся источником для проверки полноты переноса. Можно собирать требования
   и описания ошибок без персональных данных, не меняя production.
2. Не требуется ждать полной готовности Command Center, чтобы разрабатывать
   уже перенесённый проект через облачный Codex. Это отдельная разрешённая задача
   выбранного репозитория; автоматическое управление им самим Commander ещё не готово.
3. Для первого такого задания проверить актуальные refs/контекст/границы переноса,
   выбрать правильный parent PR, подтвердить воспроизводимый build/test на
   синтетических данных. Не объявлять код полностью перенесённым по наличию repo.
4. Один проект и одна ограниченная задача на ветку/PR. Разные проекты могут
   развиваться параллельно в отдельных облачных задачах. Не смешивать credentials,
   рабочие директории, DB или production-доступ. В одной ветке не вести два
   независимых изменения одних и тех же файлов.
5. Обычная итерация с iPhone: репозиторий + задача + acceptance → проверенная база →
   отдельная ветка → tests → PR/CI → короткий отчёт. Windows не нужен для сборки
   или передачи уже доступного кода. Merge/deployment остаются отдельными действиями.

Приоритеты владельца: запустить сам Command Center; Ваниль и LNAuto — высокие
бизнес-приоритеты, Capital Lab — ниже. Это не разрешение начать изменения этих
проектов в текущем задании. Их код/PR/settings/CI не изменялись. Ближайший
ускоритель для следующей отдельно разрешённой project-задачи — подтвердить её
облачную базу и воспроизводимые тесты, затем брать маленькое MVP-изменение.

## Команды проверки Command Center

- `git status --short`, `git branch --show-current`, `git log -1` — исходная точка.
- `.venv/bin/ruff check src tests scripts infra/vps`
- `.venv/bin/python scripts/export_contract.py --check`
- `.venv/bin/pytest infra/vps/tests -q` — offline infrastructure suite.
- `npm ci --prefix web` и `npm run --prefix web build`
- `scripts/cloud_test.sh [tests/paths]` — требует подготовленных локальных
  синтетических PG/Redis и secret bindings; runtime-тесты требуют точных образов.
- `scripts/verify_cloud.sh` — полный clean-source контейнерный прогон; собирает
  образы exact SHA, выполняет security/dependency gates, Python, backup/recovery,
  watchdog/cancellation и Telegram/coding smokes. См. `.github/workflows/f1.yml`.

Не применять локальный compose runbook к VPS. Docker-среда, proxy/CA, registry
и свободный диск должны быть реально доступны; ограничения платформы не обходить.
Отсутствующие prerequisites перечислять, не подменять новым результатом старого CI.

В handoff каждой задачи сохранять repo/branch/base SHA, scope, изменённые файлы,
коммит/PR, команды и результаты, CI, неразрешённые внешние intents/резервы,
точные блокеры и один следующий безопасный шаг. Временный workspace не архив.
