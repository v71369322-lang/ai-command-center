# Критическое ревью F1: текущая облачная итерация

Отдельная последующая проверка PR #8 и исправления:
[REVIEW_PR8.md](REVIEW_PR8.md). Она выполнена в отдельной ветке, но той же
сессией; полностью независимое внешнее заключение по-прежнему не заявляется.

Это review выполняющего агента, не отдельное независимое заключение другого
reviewer. Независимый verifier результатов исполнения — отдельный механизм и
не заменяет независимое review значимого изменения H-D05/H-I10.

## Отключённый черновик recovery-профиля

Это review выполняющего агента. Новый operator-only helper не создаёт F1 tasks,
grants, tokens или deployment и не конструирует HTTP/DB clients. Исторический
профиль связывается с local inspection по digest, report age и фиксированной
задаче. Отчёт не превращается в authority: будущий RecoveryExperiment.verify_parent
и observed owner consent остаются обязательными. Расход плюс один новый резерв
должны помещаться в старый grant budget и прежний общий потолок.

В output принудительно disabled mode, live_authorized=false, tariff.confirmed=false,
пустые финансовые/evidence references и неподтверждённый баланс. Сохраняются
исторические числовые параметры, не свежесть или полномочия. Создаётся новый
private каталог вне active state/source, по plan pin входных bytes и output path;
0600 exclusive writes не повторяются поверх полного или частичного результата.
Путь к provider credential принимается только как прежний фиксированный container
reference; значение credential не читается. CLI скрывает validation/IO/argument
text. Это cloud preparation, не owner host/paid authorization.

## Операторский read-only отчёт перед восстановлением

Это review выполняющего агента. Reader принимает только фиксированный task ID
и существующий локальный broker environment. В PG применяются READ ONLY и
REPEATABLE READ; RuntimeLedger constructor, Store.transaction, mutating methods,
heartbeat, grants, provider HTTP и token issuance не вызываются. SQLite использует
mode=ro/query_only и старый verifier; неподдерживаемый WAL отклоняется до открытия.
Docker ограничен прежним Unix/rootless preflight и точным ps -a. Ошибка daemon
или отсутствие runtime evidence не подтверждают очистку.

Ответ содержит только fixed flags, числовой учёт и hashes. Model response,
config references, credentials и exception text не выводятся. Provider key values
не читаются; DB settings остаются в trusted broker. Диагностика не является
RecoveryExperiment.verify_parent и всегда оставляет authority/consent false.
Проверки с настоящим PG и SQLite подтверждают запрет записи; это не новое host
acceptance. Low B110 используется только для редактирования ошибок декодирования;
внешние ошибки не становятся положительным результатом.

## Однократный восстановительный тест, 30 октября 2026

Это review выполняющего агента. Новый фиксированный recovery scope использует
прежний F1 grant, audit, ledger и observed Telegram consent. Старые FAILED,
grant и расход сохраняются. Под PG lock проверяются исторические anchors и
ровно один завершённый OpenAI-вызов, отклонённый по контракту исходника.
Новый максимум — один вызов без исправления, резерв до 34.7868 ₽; старый расход
плюс новый резерв должен помещаться в исходный согласованный лимит.

Режим, модель, baseline, source/profile pins, verifier и broker credentials
сохраняют прежние ограничения. Отдельные namespace и callback rx: не принимают
старую карточку fx: как новое согласие. Первый grant остаётся одноразовым;
восстановление также получает только один grant на режим. Parent proof заново
проверяется перед внешним действием и после I/O. Новый manifest marker обязан
совпасть с защищённым RecoveryExperiment; SQL-миграции и новые mounts не нужны.

До VPS применения отдельно сверяются завершение исходного runtime record,
отсутствие его контейнера и свежие evidence. Cloud tests не подтверждают это
состояние хоста. Разрешение разработки не запускает paid recovery или deployment.

## GitHub App metadata.push и Git discovery

После owner-provided false push /200 Git advertisement реализован отдельный
bounded readonly discovery fallback, не безусловное удаление guard. Strict
validate_repository без сетевой projection всё ещё требует push:true. Общие
ID/name/lifecycle/admin/main/protection/BASE_SHA checks выполняются независимо
от metadata flag; projection привязана к repo/service/base. Runtime получает её
только через прежний F1 Gateway/ExternalAction/audit и проверяет authority после
I/O. Model/task/UI flags не разрешают fallback и не являются evidence.

Новый host github.com разрешён только для одного synthetic repo GET discovery
в first-experiment profile, без произвольных query/body/method и redirects.
Basic auth остаётся в trusted gateway; raw packet body не сохраняется. Parser
ограничен64KiB/256refs, проверяет полный stream и нормализует шесть полей.
Operator использует тот же parser; неясный исход не продвигает candidate и не
создаёт новый POST. Probe остаётся readonly. Наблюдение discovery не выдаёт
task/deployment consent и не гарантирует будущие branch-rule/REST write results.
Это review выполняющего агента, не независимое внешнее заключение.

## Telegram preparation: единственная waiting AI-задача

Новая `/prepare_experiment` вызывает общий с API fixed owner-only creator, а не
Gateway.authorize. Никаких provider calls, финансового approval, ExternalGrant,
executor outbox или automatic resume. Task/link/receipt/reply атомарны в прежней
F1 transaction; source/owner/private-profile/epoch/120sec/binding guards защищают
от отложенного создания и замены существующей задачи. Plain text не передаётся
в first-experiment payload; клиентские CRM-данные не используются. Actual payload
digest проверяется дополнительно к равенству JSON. Existing ledger/reserves не
меняются, UNCERTAIN reply не пересылается. Это review выполняющего агента;
независимый внешний reviewer и реальные host/phone acceptance не заявляются.
Отдельный девятый named transition d932baaf→7467df2 сохраняет прежние восемь
source pairs/default и требует прежний explicit integration/readiness binding.
Scope/byte-pin/custody/source/images/previous-bundle/deadline/journal checks не
ослаблены; новый target нельзя применить под прежним именем пакета.

## Telegram polling latency, 30 октября 2026

Проверка наличия NEW delivery текущего profile влияет только на getUpdates
timeout, без чтения body/credentials и выдачи полномочий. Отправка остаётся после
обработки входящих controls: перенос sends перед poll или между updates мог бы
задержать уже ожидающий `/stop` сетевым ожиданием. Этот порядок сохранён и
закреплён PG/MockTransport tests. Предел20deliveries, source/connection/leadership
guards, rate-limit/backoff и запрет повтора UNCERTAIN прежние.

Idle default2секунды вместо10 увеличивает частоту Telegram requests, но не
создаёт AI calls или новые threads/clients. SENT/UNCERTAIN/SENDING/CANCELLED и
чужой profile не включают timeout0. Cloud tests проверяют протокол, а не реальную
VPS/phone latency. Named release pins и уже собранные owner images не меняются;
новый код требует отдельной доставки exact-source images.

## Исправления

| Находка | Последствие | Исправление / проверка |
| --- | --- | --- |
| CANCEL_REQUESTED превращался в RECONCILING при expired lease | После сверки отменённая операция могла стать кандидатом owner retry | Сохраняется намерение отмены; regression test запрещает retry после reconciliation |
| compare_digest(str) не принимал не-ASCII credential | Неавторизованный запрос мог вызвать 500 | Сравнение bytes, ограничение длины; negative auth test |
| Короткий контейнер мог завершиться до inspect | Результат принимался без фактической проверки isolation metadata | Обязательный inspect перед принятием результата; fail closed/security trip |
| JSON true сравнивался с integer fence 1 | Нарушение строгого контракта manifest | Проверка точного типа int перед сравнением |
| Validation error мог повторять входные данные | Случайный секрет мог попасть в error response | Общий безопасный 422; OpenAPI обновлён; negative echo test |
| Secret fields попадали в dataclass repr | Возможная утечка при диагностике | repr=False для credentials; regression test |
| UTF-8 данные раздувались ASCII-escaping между API и executor | Валидная Unicode-команда могла превысить input limit | Ограничение байтов и компактный UTF-8 transport; real executor regression |
| Resume при ещё неизвестном исходе | Некорректное представление готовности контура | Запрет до завершения reconciliation; pending grants отзываются |
| Forecast не учитывался в отображаемом threshold | UI мог показывать 0 при budget restriction | Threshold по max(actual+reserved, forecast); regression test |
| Audit denial блокировал async event loop | Риск задержки управляющих запросов | Offload в bounded thread pool; bounded HTTP rate state |
| Worker получал owner/operator bearer secrets | Ненужные credentials у launcher | Worker не монтирует identities; API/agent boundaries сохранены |
| Recovery CLI мог наследовать удалённый Docker context | Риск случайного обращения к другому daemon | Единый local_docker и shell wrapper: Unix socket, selectors удаляются, proxy/CA/registry сохраняются; regression без сетевого обращения |
| В dev-lock использовался pytest 8.4.2 | Аудит выявил PYSEC-2026-1845 (дублированный advisory для одной уязвимости) | Обновлён pytest 9.1.1; аудит теперь охватывает runtime и dev dependency closure |

## Решения в пределах разрешения F1

- Контейнерный worker — тот же доверенный launcher с полномочиями локального
  облачного Docker daemon, а не новый административный сервис. API/executor
  socket не получают. Никакого privileged/host networking или доступа к VPS.
- Docker CLI закреплён digest; app/worker — разные build targets. Секреты
  остаются runtime mounts, в образ не копируются.
- 60 requests/min/IP и bounded LRU на 1024 источника — DERIVED профиль F1.
  Это дополнительная защита, не durable authorization и не distributed rate limit.
- Audit проверяется streaming batches, без загрузки всей цепочки в память.
- Дополнительный restore drill использует другой контейнер PostgreSQL, tmpfs,
  network=none, без портов. Local trust включён только в disposable drill;
  primary PostgreSQL settings не меняются. Это не offsite disaster recovery.

## Статический анализ: явная triage, без подавления результатов

Bandit сохраняет полный JSON. MEDIUM/HIGH, ошибки scanner и новый неразобранный
LOW rule блокируют verify_cloud.sh. Для текущих LOW rule выполнен review:

- B404/B603/B607: argv-based subprocess без shell=True; команды локального Docker,
  Git и security tools. Не исполняются команды/пути из недоверенных сообщений.
  Endpoint фиксирован Unix socket; Docker PATH внутри worker — readonly image.
- B110: отказ журналирования или недоступная PG в cleanup не создают разрешение
  и не объявляют success; исполнение останавливается, evidence удерживается.
- B105: boolean `admin_db_secret_mounted: False` — факт проверки mounts, не пароль.

Последующая итерация bounded operations добавляет в тот же scan также
`infra/vps/operations`, без расширения списка разрешённых LOW rules. Subprocess
там ограничены fixed argv Git/OpenSSL/systemd и test-only UID proof. Enrollment
проверяет Git commit/tree/blob identities и выполняет Git как unprivileged runner.
SHA-1 с usedforsecurity=False используется только как формат Git object ID;
владельческое разрешение дополнительно фиксирует SHA-256 bootstrap/catalog.
Private receipt key создаётся как acc-control; root не запускает его Python venv.
Результаты операций подписываются стандартным Ed25519, проверяются cryptography
и OpenSSL. Ключ не доступен runner, API или coding executor. Shared host/daemon
compromise не исключён этой схемой. Полномочия и resource limits описаны в
[BOUNDED_OPERATIONS_CHANNEL.md](../infrastructure/BOUNDED_OPERATIONS_CHANNEL.md).

SQL interlock строится через psycopg.sql.SQL/Literal, не через конкатенацию
неэкранированных данных. Полный набор LOW наблюдений не удаляется из отчёта.
Это triage текущего кода, а не независимое security certification.

## F34 operator helper

В scan добавлен infra/vps/stage_telegram_update.py. Его две LOW B105 относятся
к сравнению token_file с фиксированным in-container путём /run/telegram/token.
Это ссылка на защищённый binding, не значение credential. Staging вообще не
открывает token; approved apply делегирует прежний credential preflight trusted
Deployment. Оба наблюдения сохраняются в Bandit JSON. LOW allowlist не изменён,
новые MEDIUM/HIGH или неизвестные rules по-прежнему блокируют CI.

## Первый experiment deployment binding

Новый deployment_integrations проверяет config/credential custody через
O_NOFOLLOW descriptors. Значения keys при prepare/preflight не читаются;
App PEM не является installation token и превышает разрешённый size cap.
Полный byte pin дополняет прежний profile hash, исключающий credential paths:
redirect reference на другой runtime secret отклоняется ещё loader до Gateway.
Readonly config находится только в API/broker, keys и opt-in egress только в
broker. Прежний запрет произвольных mounts/env/networks остаётся для defaults.
Binding не выдаёт grants и не ослабляет budget/final confirmation guards.

В retained Bandit JSON добавились8 LOW observations: B105 — фиксированный
in-container `/run/f2/github.token`, не secret value; B404/B603/B607 нового
networkless cloud smoke — argv-only Git/local Unix Docker для exact source
и публичных disposable fixtures, без shell=True/недоверенных task inputs.
MEDIUM/HIGH отсутствуют в локальном scan. Allowlist rules не расширялись,
findings не подавлялись. Полный dependency/static scan final SHA — в CI.

Следующий mobile opt-in добавляет readonly config Telegram без credentials,
новых сетей или grants; legacy binding без флага остаётся прежним. Postcheck
проверяет actual mount/pin. В public-fixture smoke точечно отмечен B106:
`token_file='/run/telegram/token'` — fixed container selector, не значение токена.
Только этот false positive имеет локальный nosec с объяснением; список разрешённых
Bandit rules не расширяется. Остальные retained findings продолжают проверяться.

Cloud reader `/experiment` ограничен точным owner request key/payload и creation
audit, source pin, grant digest/anchor и прежним Gateway ledger digest check.
Он не создаёт Gateway/HTTP clients, не читает credentials, не выдаёт grants и
не вызывает reconciliation. PR URL выходит только после completion/verification
anchors и exact synthetic-repository URL validation. SETTLED трактуется как
неопределённый результат в status так же, как в существующем no-repeat guard;
settled money не означает полученный результат. Cached live fixtures не являются
внешним live evidence. Новый reader не добавляет network/file execution sinks.

Experiment notices требуют явный owner/private receipt с immutable intent и
fingerprint, audit ordering и профиль/source/task binding. Collector повторно
использует верифицирующий snapshot без Gateway/client construction. UTC timestamp
исключён из semantic delivery key; уже существующие SENT/UNCERTAIN/CANCELLED
delivery не переиспользуются как NEW. Unsubscribe меняет только известные NEW
notices и сохраняет начатые/неопределённые sends. Схема и финансовые/F1 grants не
меняются; rootful mocked results не означают внешние live evidence.

Отмена первого эксперимента связывает private-owner receipt с UUID/payload при
приёме команды, source и сроком 120 секунд. Перепривязка request key не меняет
цель. Cancel и inbox/reply commit атомарны под прежним Control lock; DONE receipt
не применяется повторно. Внутренний locked F1 cancel сохраняет прежние roles,
operator ownership и переходы; новый путь не создаёт Gateway/HTTP/credentials.
Accounting/grants/reserves не изменяются даже при отмене во время HTTP. Неизвестный
исход сохраняет no-repeat; подтверждение намерения не обещает фактической остановки.

Operator-only GitHub token preparation связывает clean source/public key/paths
с reviewed plan и свежим owner deadline. Credential creation ограничена одним
POST с exact repository ID/permissions; effective token count и baseline читаются
после выдачи, runtime/config/grants не меняются. Unknown outcomes и partial files
не перезаписываются и не разрешают автоматический повтор. Scoped-token count
не выдаётся за полное число repos установки. PEM/JWT не передаются runtime.

Security scan теперь включает prepare_github_token.py. Его6 новых retained LOW:
B404/B603/B607 — argv-only local Git с удалением inherited GIT_* selectors;
B105 — fixed enumeration endpoint и два boolean status fields, не credentials.
Ни одно наблюдение не подавлено, allowlist не расширяется; MED/HIGH блокируют CI.
Текущая triage не является независимой сертификацией custody host/private key.

Следующее operator-only исправление удерживает response-bound candidate0600 до
дальнейших GET, сохраняя запрет финального credential при отказе. Stage, HTTP
status и allowlisted error/boolean checks диагностируют failure без provider
body, token/JWT/paths. Inspect offline не читает credential; явный probe читает
только private hash-bound unexpired candidate, его client capability запрещает
POST/App endpoints. Probe не меняет receipt/files/authority и не продвигает token.
Legacy lost credential не восстанавливается выдуманным receipt или новой выдачей.
Strict runtime validate_repository и прежние source/approval/custody guards
сохранены. Новый retained LOW B105 относится к boolean token_issued_by_inspection,
не secret value; всего99 reviewed LOW, без расширения allowlist или suppression.

## Явное платное подтверждение Telegram

Двухшаговый authorize не дублирует F1 grants: общая локальная Gateway composition
вызывает прежний Store.approve, затем сужающий ExternalGrant. API typed consent
сохраняется; Telegram предоставляет отдельный private-owner observed-card consent.
Pure scope validation при показе карточки не записывает разрешение. Нет нового
HTTP/credential capability, schema, scheduler, автоматического resume или renew.

Source/profile/connection, immutable task/version/epoch, price/budget/config и
credential references привязаны к карточке. SENT с observed message ID и queued
body digest исключают применение неизвестной/подменённой отправки. Повторная
проверка под Control lock и срок120секунд ограничивают delayed clicks. Scope
installer коммитит grant/READY/outbox/consumed/reply атомарно; failure до commit
откатывает всё, потеря результата после commit не повторяет grant. Изменение
runtime config между review и commit, stop/resume и recovery блокируют карточку.
Существующие runtime gates/ledger/no-repeat сохраняются. Публичные live-shaped
fixtures не подтверждают реальные credentials/финансы/публикацию или VPS readiness.

## Офлайн-граница планирования saved requests

Новый context formatter/response parser не является scheduler/authority/provider
client. Owner-only snapshots используют прежние immutable intake/project/audit
проверки и current source/control binding; review повторяет read-only проверку
под Control lock. Project label не даёт repository access. Existing sensitive
content screen переиспользован перед context export и во всех plan strings;
credential files/config не открываются, screen не объявляется универсальным.

Developer rules отделены от untrusted request data. Strict extra-forbid schema,
size/list/string/usage/model/context checks и запрет tool/refusal/multiple outputs
ограничивают структуру предложения. Duplicate JSON keys не принимаются, ошибки
не включают provider body или Pydantic inputs. Естественный язык не проверяется
как безопасная executable программа: даже shell/URL/permissions в text остаются
текстом, без запуска/перехода/гранта. Ответ не подтверждает provider provenance,
usage/billing evidence или качество плана. Никаких DB writes, task/grant/outbox
созданий, live I/O, нового API/Telegram route, schema или deployment transition.

## Durable advisory drafts и Telegram readback

Owner-supplied response сохраняется только после прежнего locked snapshot/contract
review, в одном bounded append-only audit event. Role/source/normalized document
hash/identity/per-request version/strict false flags проверяются reader; JSON
bool/numeric coercion не подменяет schema/authorization. Никакого provider/billing
provenance не выводится из response ID или usage. Модель не имеет доступа к writer
или trusted composition hook. Unknown provider I/O этим кодом не повторяется.

100records/32KiB per document, отсутствие raw response/intake text, sensitive-content recheck,
exact dedup/conflict и atomic receipt composition ограничивают retention/повтор.
Содержимое draft остаётся чувствительным пользовательским текстом в существующей
private PG/audit и backup; универсальной secret detection или semantic plan safety
нет. Нет удаления/перехода в исполняемую задачу и финансовых изменений.

Private-owner/profile-scoped reader скрывает stale body и закрепляет version/page;
новый черновик не подменяет продолжение старого. Plain-text ответ имеет постоянную
метку unverified proposal. Каждая команда даёт≤1bounded delivery, не fan-out всех
страниц. Existing source/credential/runtime guards, rate limits, inbox replay и
UNCERTAIN no-resend сохраняются. Hook/reader не меняют F1 execution authority.

## Closed planning gateway поверх F1

Новый kind всегда owner-only WAITING_APPROVAL. Immutable/current request payload
проверяется в Store.create, scope approval и перед I/O/result acceptance. Узкий
ExternalGrant не заменяет прежний F1 Approval. Общий role/lease/fence/source/
grant anchor guard и financial request/ledger implementation переиспользуются;
coding и planning purpose checks остаются разными. Exact-context grant dedup,
constant single-call key, endpoint/body whitelist и unresolved-request prohibition
не позволяют сменой creation key/context обойти no-repeat. Generic APIs не
создают и не одобряют planning scope; production broker блокирует dispatch.

Mode live отсутствует, ключевых files/env bindings нет, constructor принимает
только MockTransport и public mock credential. Это closed backend без новых
реальных полномочий сети/расходов, не дополнительный permission system.
Response settlement использует admitted tariff copy; profile mutation не
переоценивает уже отправленный request. Перед дальнейшим принятием результата
действуют прежние revocation/config guards. Draft+result commits атомарны,
подтверждённый mock spend не откатывается вместе с invalid/local-failed result.
Completed response переиспользуется локально, unresolved outcome не отправляется
повторно. Никакой semantic/model quality либо live provenance этим не доказаны.

Generic synthetic Runner не получает planning kind и не обещает отсутствие
external effects через container reconcile. Watchdog сохраняет unknown usage
для нового kind; его container-absence proof не является provider-outcome proof.
Новых schema/mount/egress/runtime/deployment transitions нет; live планировщик
требует отдельной реализации и проверки всех interlocks.

## Не закрывать без внешнего evidence

Host-compromise isolation, независимая custody/immutability checkpoints/backups,
key escrow, watchdog и emergency access, VPN/HTTPS/MFA и реальные VPS quotas.
Контейнеры одного Docker daemon не являются независимыми failure domains.
RPO≤15min/RTO≤4h остаются provisional. Исходные owner requirements не ослаблены.
