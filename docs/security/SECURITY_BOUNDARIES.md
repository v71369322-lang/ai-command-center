# Границы безопасности

APPROVED — ограничения R; предлагаемая карта угроз, проверок и блокировок DERIVED. Способы реализации OPEN, не выбраны по умолчанию. [Реестр R](../requirements/REQUIREMENTS_REGISTER.md), [D](../decisions/DECISION_REGISTER.md).

| Граница | Недоверенный вход / угроза | Обязательный контроль | Проверка (предложена, не выполнена) | OPEN |
| --- | --- | --- | --- | --- |
| Владелец → Telegram/web → API | Подмена личности, повтор согласования, старый экран | R03,R12,R13: единая версия, точное действие, срок и независимая проверка | Чужая идентичность, изменённые параметры, истёкший срок и отзыв отклоняются | D23 |
| Оркестратор → исполнитель | Исполнитель запрашивает больше прав или ресурсов | R14,R16,R17,R18,R28,R38: минимальные права, изоляция, остановка, лимиты | Запрет доступа к другому проекту/среде, prod и управляющему серверу; после отзыва новых действий нет | D21,D25 |
| Внешние тексты/AI → управляющий контур | Prompt injection и ложный отчёт о завершении | R06,R19: результат — данные, полномочия не выводятся из текста | Встроенная команда раскрыть секрет/снять тест не исполняется; без доказательства нет завершения | D19,D22,D29 |
| Данные/секреты → задания/логи/провайдеры | Утечка секретов, персональных данных, межпроектный доступ | R15,R18,R20: запрет автоматической передачи, минимизация доступа | Синтетические маркеры не проходят в неразрешённый канал; реальные данные не используются | D25 |
| Worker → внешнее действие | Таймаут после уже совершённого эффекта, перезапуск | R11,R21,R22: журнал и сверка перед повтором | Сбой после эффекта не порождает второй эффект; неизвестность явно сохраняется | D20,D22 |
| Планирование → платный запуск | Гонки резервирования, неизвестные расходы, бесконечные исправления | R27,R35–R40: максимальный резерв и ограничения; защищённые расходы | Конкурентные задачи не превышают лимит; неподтверждённая стоимость не исчезает | D24 |
| Git/CI → выпуск | Подмена артефакта, ослабление тестов, несовместимая БД | R23,R25–R27,R33,R34,R51 | Прослеживаемость до коммита/CI, независимая проверка; небезопасный откат блокируется | D27; формат provenance не выбран |
| Управляющий VPS → восстановление | Компрометация приложения/сервера, уничтожение журналов и копий | R28,R30–R32: независимые доступ, мониторинг и защита копий | Компрометированная идентичность сервера не уничтожает все восстановительные данные; восстановление проверено | D26 |
| Центр → самостоятельный проект | Действия вне разрешения, перенос CRM, возобновление паузы | R45–R47: отдельное разрешение и права | Отсутствие интеграции по умолчанию; запреты торговли/клиентских сообщений/расходов | D28 |

Независимость проверки разрешений не означает выбор отдельного сервиса: модульный монолит остаётся утверждённым. Конкретный механизм независимости должен исключать принятие решения самим исполнителем и пройти ревью. Docker Compose сам по себе не считается доказательством изоляции AI-задачи.

Аварийная остановка не обещает отменить уже совершённую необратимую операцию. Предлагаемая проверка различает запрет новых действий, отзыв прав, фиксацию выполняющихся операций и последующую сверку фактов. Канал независимого доступа и время реакции ещё не выбраны.

При компрометации управляющего сервера локальный журнал нельзя считать единственным достоверным источником восстановления. Независимые права, хранение и проверка копий требуют проектирования D26; конкретный поставщик, WORM или система секретов не утверждены.

Этап 0B не использует реальные ключи, клиентские данные, внешние проектные API, платные AI-вызовы или производственные сервисы. Ориентир бюджета не является разрешением покупки.

## Дополнение Stage 0C-1: нормативные уточнения

Источник [SRC-0C1](../history/stage-0c-1/SOURCE_PACKAGE.md), класс OWNER_APPROVED_SUMMARY, [матрица](../history/stage-0c-1/RECONCILIATION_MATRIX.md). H-A05/H-B01 разрешают автономность только безопасных обратимых задач внутри явных прав, лимитов и утверждённых требований. H-A06 требует согласия владельца на production deployment, необратимые действия, существенные архитектурные изменения, новые обязательства расходов и внешние действия перед клиентами. Бюджет 10 000 ₽ не является обходом согласования новых обязательств.

H-A07 делает policy layer независимым и детерминированным: суждение AI не может разрешить обход. H-B07: предложение и вопрос без ответа не являются согласием. H-A11 сохраняет остановку владельцем без выдачи агентам неограниченных инфраструктурных credentials.

H-B08 применяет аутентификацию и те же правила согласований к Telegram voice; транскрипция сама по себе не даёт разрешения на опасное действие. H-B09 требует безопасной обработки screenshots, PDF, spreadsheets и attachments. Конкретные парсеры, модель доверия, хранение и провайдер транскрипции не выбраны.

H-A08/H-A09 требуют атрибуции, долговечности записей и сквозной связи доказательств. H-A10 требует независимости critical monitoring/emergency controls/audit history/backups от AI providers, в дополнение к ранее указанной независимости от сервера. Предлагаемые проверки отсутствия AI override и отказа AI providers — DERIVED; они не выполнялись. Открытые детали: [U02,U04–U07](../history/stage-0c-1/CONFLICTS_AND_UNCERTAINTIES.md).

## Дополнение Stage 0C-2: autonomous development controls

Источник [SRC-0C2](../history/stage-0c-2/SOURCE_PACKAGE.md), OWNER_APPROVED_SUMMARY; [матрица](../history/stage-0c-2/RECONCILIATION_MATRIX.md), [impact](../history/stage-0c-2/IMPACT_REPORT.md). Граница safe reversible self-repair (H-C05/H-D07) не позволяет ослаблять требования, tests, budgets, permissions, acceptance или обходить approvals. H-D06 требует bounded verification/escalation разногласий; бесконечный debate loop и self-authorized safety-limit changes запрещены.

H-C08 допускает priority changes только для verified critical incidents в уже approved incident policy. Норма не отменяет owner priorities H-B11/H-B12, exact consent H-C09 и deterministic policy H-A07. H-C10 approval cards явно показывают action, scope, risk, expected effects, relevant versions, expiry; unanswered card не является согласием.

H-D03/H-D10 требуют scoped file/API/network/credentials и dedicated Git branches/worktrees; агенты не получают unrestricted VPS admin, production DB, cross-project credentials или unrelated data. AGENTS.md не отменяется: additional worktree сейчас не запрошен и не создаётся. Точная технология изоляции OPEN.

H-C12/H-D04/H-D05: risk-appropriate static/unit/integration/contract/E2E/security checks; significant changes имеют независимое AI code review дополнительно к deterministic tests; key milestones/MVP/production принимаются владельцем. AI review не является owner consent или доказательством всех проверок.

H-D09/H-D11: staged exact-release consent, verified artifacts, trusted CI evidence, dependency review, pinned source revisions, release integrity и post-release health. Сохраняется запрет unsafe rollback и auto-rollback необратимых DB migrations. H-D12: mocks/sandboxes где возможно, real-call tests только явно разрешённые, safe rate-limit/idempotency/ambiguous outcome handling.

Будущие проверки в impact — DERIVED, не выполнены. Не добавлены код, real calls, secrets, paid services, deployments или VPS configuration/tests; бюджетный ориентир не purchase permission. CRM автосервиса PAUSED; Capital Lab и CRM кондитерской самостоятельны, бизнес-операции/клиентские сообщения не разрешены.

## Дополнение Stage 0C-3: confirmed security/recovery summary

Источник [SRC-0C3](../history/stage-0c-3/SOURCE_PACKAGE.md), OWNER_APPROVED_SUMMARY; [полный impact](../history/stage-0c-3/SECURITY_AND_RECOVERY_IMPACT.md). Прежние записи и исторические статусы сохранены; следующие нормы не являются свидетельством выполненной реализации.

H-F04: независимая deterministic policy контролирует actual credentials/permissions, unknown actions blocked, AI review не override. Это не требование нового microservice. H-F06: external messages/files/sites/tool outputs/repository content — untrusted data с provenance/instruction separation, network/secret/exfiltration restrictions, suspicious-action blocking и adversarial tests.

H-F02/H-F10: applicable localization obligations требуют разделить control processing и customer data, minimize/deidentify/restrict APIs, проверить logs/backups/tasks/legal basis/hosting/international transfers до real-data use. Dev/staging/prod изолируются credentials/DB/network/data policy, synthetic default; real changes exact approval, staging may be on demand. Юрисдикция и compliance не выводятся из RUB/языка/VPS, customer data сейчас не читаются. Scope real changes vs safe granted autonomy — OPEN U3-04/U3-11.

H-E04/H-E11/H-F13: только bounded preauthorized safe reversible remediation/containment, без privilege escalation/destruction of evidence. При compromise stop unsafe actions/revoke exposed permissions/independent alerts/preserve protected logs/backups/investigate/reconcile; dangerous resume — owner approval. H-E06/H-F03: protected offsite backups/tested restoration; production data/DB restore требует owner approval. Planned recovery не tested recovery, RPO/RTO performance не доказаны.

H-E09/H-F03/H-F05/H-F15: watchdog/alert/console emergency path вне primary failure domain и без default second permanent VPS; Telegram/web/monitoring/history/emergency работают без AI. Jobs pause/reconcile, fallback лишь verified-compatible rights/data/budget; потеря control блокирует новые dangerous actions, bounded leases/heartbeat/expiry и supported stop/quarantine не гарантируют instant kill внешнего job.

H-E05/H-F07/H-F08/H-F09/H-F11/H-F12: bounded dependency protection, pinned approved requirements/contracts/Git base с revalidation, не повышаемые AI limits, independent completion evidence, unique operations/idempotency where supported и concurrency/version/expiry/fencing controls. Ambiguous dangerous effect → pause dependents/reconcile, не blind retry/stale overwrite. Точные caps/TTL/ретенция/locking implementation не выбраны.

H-E08/H-F01: hard ceiling 10 000 ₽/месяц без explicit approval на превышение, 70 warn/90 restrict optional/100 block new nonessential paid work, прежние warnings сохраняются. Essential security/monitoring/backups защищены, но silent exceed и new commitments даже ниже ceiling не разрешены. Forecast/delayed/unconfirmed accounting не игнорируются и не суммируются вымышленной формулой.

H-F14/H-F16: перед future deployment/production отдельно разрешённый preflight required APIs/region/terms/legal/cost без prohibited circumvention; exact source/dependency pins/checksums/test-security/provenance, release only exact approved artifact, no unrestricted production release secrets у coding agents. Сейчас preflight/VPS access/deployment/paid actions запрещены; R34 о safe rollback и необратимых миграциях сохраняется.

## Дополнение Stage 0C-4: analytics/pilot и planned infrastructure controls

Источник [SRC-0C4](../history/stage-0c-4/SOURCE_PACKAGE.md), OWNER_APPROVED_SUMMARY; [impact](../history/stage-0c-4/ANALYTICS_AND_INFRASTRUCTURE_IMPACT.md). Все прежние deterministic policy/default deny, exact approvals, prompt-injection/data/env isolation, bounded execution/reconciliation и protected evidence требования сохраняются.

H-G02/H-G03/H-G10/H-G12: authoritative KPI/source/version/freshness и privacy/lawful identity reconciliation, scoped evidence drill-down. [Ytimes/storefront note](../history/stage-0c-4/SOURCE_PACKAGE.md#confectionery-double-counting) запрещает double count; join/matching/blanket exclusion rules не выбраны, uncertain customers не verified. Analytics role/report не открывает customer databases или international transfers автоматически.

H-G07/H-G13: recommendation/ranking не owner consent на outreach/spending/production/business action, positive forecast/ROI не permission. Ytimes/Bitrix24/VK/T-Invest/brokerage/customer/other production data не подключаются; no real customer data processing. Applicable localization/legal/log/backup/task/API review H-F02 сохраняется без вывода юрисдикции из planning Almaty/RUB.

H-H03/H-H05: initial Ubuntu LTS/pinned Compose, SSH keys/restricted admin/firewall/HTTPS/MFA where appropriate/updates и least-privilege controlled secrets broker or equivalent — source-backed **future approach**, не current VPS security proof. Нет выбранного broker vendor, unrestricted VPS admin/release credentials или нового microservice; H-H04/H-H13 требуют CRM/Radmin separation и no convenience-only services.

H-H06/H-H09/H-H10: protected offsite/PG WAL-PITR where feasible/integrity/drills, provisional RPO≤15min/RTO≤4h без гарантий, independent monitoring/emergency/recovery без automatic second permanent VPS. Production restore/dangerous resume exact approval сохраняются; irreversible DB migrations не auto-reverse.

H-H07/H-H08: hard 10 000 ₽ ceiling/70-90-100 controls и essential protection без silent exceed, on-demand scope/time/cost/concurrency/cleanup; new commitments ниже потолка и additional permanent capacity owner-approved. H-H11: isolated synthetic E2E starting pattern, real projects/data только separate secured pilots. Это не scope expansion MVP и не acceptance evidence A01.

[OPS-C status](../architecture/INFRASTRUCTURE_STATUS.md) остаётся owner-reported purchase/impaired console, current config/OS/provider/region/security/billing/readiness unverified. Никаких server/preflight/paid/real business actions или actual-data tests сейчас.

## Stage 0C-5: master security и operational acceptance

[Source H-I/H-J](../history/stage-0c-5/SOURCE_PACKAGE.md), [final audit](../history/stage-0c-5/FINAL_ARCHITECTURE_AUDIT.md). Все прежние hard budget/owner approvals/localization/prompt-injection/least-privilege/isolation/reconciliation constraints сохраняются.

H-I14 уточняет one-owner MVP, extensible RBAC, **mandatory secure web MFA**, verified Telegram owner binding, appropriate critical step-up, exact action/parameters/version/expiry. Это не утверждение auth provider/protocol; SG02 должен закрыть concrete policy до реальных owner channels. Unknown action blocked, fixture auth не MFA/binding evidence.

H-I08/H-I15/H-I17: temp scoped credentials/network/files/API/Git isolation, preserve artifacts/evidence до disposal, secrets вне Git/ordinary tasks, rotation/emergency revoke/API proxying where needed; no real brokerage trading credentials coding agents. Kill switches на task/agent/project/unsafe-op уровнях сохраняют essential monitoring/backups/audit; dangerous resume owner-approved, no unsupported immediate external kill.

H-I06/H-I11: durable records PG authoritative, Redis не sole truth, unique ops/leases/crash/external reconcile; no exactly-once promise. H-I12/H-I16/H-I20/H-I23: CI/staging/compatible migrations/backup-key-config recovery/fault injection/security/restore/runbooks/watchdog/cost audit и exact production/go-live approval. Key recovery не означает помещать key material в Git/task packets; RPO/RTO provisional, production restore approval, no irreversible DB auto-reverse.

H-I21/H-I22: synthetic first, later tentative Capital Lab read-only pilot лишь individually owner-approved; CRM может следовать, автосервис PAUSED. Pilot metrics до запуска, zero unauthorized actions/leaks/budget breaches/unresolved critical failures, autonomy expansion owner-approved. Никаких real integrations/customer/brokerage/provider/server/preflight/paid actions сейчас.

[Classified ledger](../history/stage-0c-5/CONFLICTS_AND_UNCERTAINTIES.md) не снимает guards: later methods OPEN, обязательные нормы уже source-backed. Actual CI/security/restore/operational performance evidence отсутствует; documentation review не программирование/расходы/deployment permission.
