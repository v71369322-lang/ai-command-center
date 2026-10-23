# Влияние на monitoring, security и recovery

Нормативный источник: [SRC-0C3](SOURCE_PACKAGE.md), [29 записей OWNER_APPROVED_SUMMARY](HISTORICAL_DECISION_REGISTER.md). Этот отчёт, его группировка, следствия, будущие проверки и связи с компонентами — **DERIVED**. Никаких runtime tests, actual customer data, provider preflight, access/configuration VPS или paid actions здесь нет.

## Мониторинг и интерфейс

| Область | Source / related | Влияние и ограничение | Предлагаемая будущая проверка / OPEN |
| --- | --- | --- | --- |
| Technical vs business health | H-E01; R41–R43; H-B10 | Infra и business-functional health различаются. Sales/workflow symptom сам по себе не доказывает infrastructure outage | Источник метрики и operational evidence проверяются отдельно; U3-02 |
| Adaptive notifications | H-E02,H-E03; H-B03,H-B04,H-C08 | Polling адаптивный, dedup/change detection; severity/urgency/confidence/impact определяют incident handling, quiet hours для noncritical | Повтор одного сигнала не создаёт uncontrolled notifications; cadence/thresholds не придуманы; U3-03/U3-05 |
| Early degradation и evidence | H-E07,H-E10; H-A08,H-A12,H-C03 | Trend evidence отдельно от forecast; timeline/RCA/corrective action имеет evidence links | RCA-гипотеза или прогноз не помечается подтверждённой причиной; U3-02/U3-09 |
| Dashboard и cards | H-E12,H-E13; H-B10,H-C10 | Mobile-first health показывает healthy/degraded/unknown/stale/paused/failed; card связывает exact incident/version/evidence/allowed actions/approval/outcome | Outdated observation не маскируется под healthy; разрешение из другой версии не открывает recovery; U3-03/U3-04 |

Названия шести состояний утверждены H-E12; точная state machine и thresholds ещё OPEN. Предлагаемое толкование DERIVED: unknown — не хватает достоверного наблюдения; stale — есть устаревшее; paused — выполнение намеренно приостановлено. Это не выбранная спецификация переходов. CRM автосервиса PAUSED не становится failed или healthy на основании отсутствия интеграции.

Сохраняются local quiet hours 23:00–08:00 и плановые отчёты 08:00/14:00/21:00 из H-B03/H-B04. Часовой пояс, batching/cadence и критерии genuine critical incident не выбираются из UTC среды. Operational dashboard не разрешает включить полноценную бизнес-аналитику или реальную CRM в MVP.

## Hard ceiling и защищённые расходы

H-E08/H-F01 уточняют R35–R40/D13; H-A06 по новым spending commitments сохраняет силу. Историческое «ориентир» в R35/D13 не является разрешением silently exceed. Актуальная обязательная граница: **новые расходы ≤10 000 ₽/месяц без explicit owner approval на превышение**; commitments ниже потолка тоже не разрешаются автоматически.

| Порог | Сохраняемое R39 | Дополнительная source-backed обязанность H-F01 |
| --- | --- | --- |
| 70% | Предупреждение | Warn |
| 90% | Предупреждение | Restrict optional activity |
| 100% | Предупреждение | Block new nonessential paid work |

Essential security/monitoring/backups защищаются при ограничении optional paid AI, но это не безлимитное исключение из ceiling. Максимальный резерв перед paid task (R37), protected essential budget (R40) и owner consent остаются. При недостатке бюджета источник не разрешает молча превысить его ради essential action.

Actual, reserved, forecast, delayed billing и прежние unconfirmed costs R36 должны оставаться различимыми; forecast не является фактом, отсутствие invoice не освобождает предел по предположению. Их связь, исключение double counting, monthly period/курс/тариф, protected reserve и concurrent accounting — OPEN U3-06/U3-14. Формула учёта не изобретена.

Будущая проверка (DERIVED): simulated delayed invoice/concurrent reservations/threshold crossing сохраняет ceiling и essential protection без самовольной покупки. Она не запускалась, денег не резервировалось.

## Независимость, outages и loss of control

| Сценарий | Source | Обязательное поведение / предел |
| --- | --- | --- |
| AI provider outage | H-F05; H-A10,H-C06,H-C11,H-D02 | Telegram/web control/monitoring/history/emergency продолжаются без AI; affected jobs pause/reconcile. Fallback только verified compatible rights/data/budget; materially different dangerous action требует new approval |
| Primary control-plane failure | H-E09,H-F03; R28,R30–R32 | Watchdog/emergency alerts вне основного failure domain, independent console emergency path и recovery procedure. Permanent second VPS не default requirement |
| Loss of connection to running job | H-F15; H-D02,H-D08 | Bounded leases/expiry/heartbeats; no new dangerous actions; stop/quarantine within supported bounds; reconnection сверяет actual jobs/costs/permissions |
| Unreliable dependencies | H-E05,H-F08; H-D06,H-D12 | Timeouts/bounded retries/exponential backoff/rate limits/circuit breakers; time/spend/attempt/review-cycle/concurrency caps. Repeated failure/no progress/disagreement/limit → stop/escalate, AI caps не повышает |

Нельзя обещать instantaneous kill внешнего cloud job без гарантии provider API. Stop request, revoked credentials, actual provider stop и отсутствие новых effects — разные наблюдаемые факты. DERIVED-следствие для бюджета: потерянное соединение не является доказательством остановки оплачиваемого job; его фактическое состояние/стоимость сверяются, а не исчезают из учёта.

Источник утверждает bounded leases и controls, но не задаёт точные TTL/heartbeats/retries/backoff parameters и не выбирает queue/lock library. Никакого failover/provider call или deployment preflight сейчас нет. Независимый policy enforcement и modular monolith D03 совместимы; новая microservice architecture не выбрана.

## Backup/recovery и компрометация

H-E06/H-F03: protected offsite backups и tested restoration procedures; prod data/DB restoration только owner approval. H-F13: stop unsafe actions, revoke exposed permissions, independent alerts, preserve protected critical logs/backups, investigate/reconcile; dangerous operations возобновляются лишь после owner approval. H-E04/H-E11 ограничивают remediation/containment заранее разрешёнными safe reversible действиями без privilege escalation или destruction of evidence.

Различать:

| Уровень | Что доказывает | Что известно сейчас |
| --- | --- | --- |
| Требование восстановления | Owner-approved summary | Есть H-E06/H-F03 и прежние R31/R32 |
| План восстановления | Документированный порядок и границы | Детальный исполнимый runbook/ресурсы/ответственность ещё OPEN |
| Tested restoration | Протокол теста с exact versions, isolated data и verified outcome | Не предоставлен, тест не проводился |
| Production restoration | Exact owner-approved действие с фактической сверкой | В Stage 0C-3 запрещено |

В baseline численные RPO ≤15 минут/RTO ≤4 часов **не найдены**, найдены только OPEN упоминания. Условное safeguard в SRC-0C3 не принимается как новое target. Если владелец впоследствии передаст ранее обсуждённые цели, их статус — provisional requiring tested feasibility, не proven operational performance. Retention, RPO/RTO, места хранения и protected access не изобретаются.

R34 остаётся: auto-rollback приложения допустим лишь при доказанной совместимости; необратимая DB migration не откатывается автоматически. Recovery не является обходом этого правила или требования exact consent для production restore.

## Policy, данные и prompt injection

| Контроль | Source / прежние связи | Влияние |
| --- | --- | --- |
| Actual permissions/default deny | H-F04; H-A07,H-C09,H-D10 | Независимая детерминированная policy контролирует actual credentials/permissions, блокирует unknown actions. AI review, card и emergency не создают bypass |
| Localization/data review | H-F02; R15,R18–R20; H-D03,H-D10 | Отделить control-plane processing от applicable customer-data obligations; minimize/deidentify, restrict APIs, review logs/backups/tasks/legal basis/hosting/transfers до real-data use |
| Untrusted inputs | H-F06; R19,R25; H-B08,H-B09,H-D04,H-D13 | Messages/files/sites/tool outputs/repository content сохраняют provenance и разделение data/instructions; independent policy, network/secret/exfiltration restrictions, blocking, adversarial tests |
| Environment boundaries | H-F10; R18; H-D03,H-D10 | Dev/staging/prod разделены credentials/DB/network/data policy; synthetic default, exact approval real changes; staging may be on demand |

Applicable law, hosting region и lawful international transfers не выводятся из RUB, языка владельца или покупки VPS. Не утверждается compliance по одной архитектурной таблице. В Stage 0C-3 actual customer data не читаются и не обрабатываются.

Named controls source-approved; конкретные enforcement point, secret platform, detection signatures, data schemas, adversarial suite и сроки хранения — OPEN. Содержимое недоверенного файла/сайта/результата tool не может самовольно заменить owner instruction или открыть credentials.

## Stale actions, concurrency и release evidence

| Область | Source / related | Влияние и предлагаемый негативный сценарий (DERIVED) |
| --- | --- | --- |
| Version pinning и approval invalidation | H-F07; R07,R08,R13; H-C13 | Task pin к approved requirements/contracts/Git base, revalidation before merge/release/dangerous actions; changed relevant parameters expire approvals, conflicts escalated. Старый approval не годится к новому action |
| Ambiguous effects | H-F11; R21,R22; H-C06,H-C07,H-D12 | Unique operation IDs/durable journals/status reconcile/idempotency when supported; possibly succeeded dangerous effect → dependent actions paused, no blind retry |
| Competing writes | H-F12; R36,R37; H-C04,H-C07 | Per-object locks или equivalent controlled concurrency, optimistic versions/expiry/fencing where appropriate; stale write → re-read/recalculate safely or stop, не silent overwrite |
| Independent completion | H-F09; R06,R25,R26; H-A12,H-C12 | Commits/artifacts/trusted CI/actual external state с exact versions; ambiguous remains unconfirmed, agent report не evidence само по себе |
| Trusted exact release | H-F16; R33,R51; H-D09–H-D11 | CI pinned к source commits/dependency versions; checksums/test-security evidence/provenance; only exact approved artifact; coding agents без unrestricted prod release secrets |

Конкретные locking technology/fencing storage/idempotency protocol, CI vendor/signature/checksum format и dependency versions не выбираются. Ни actual concurrency tests, ни build/release/security tests приложения сейчас не выполняются. Synthetic default H-F10 не подтверждает A01 о достаточности одного synthetic E2E scenario.

H-F14 требует до future deployment/production verify authorized AI APIs/Telegram/GitHub/integrations access, region/terms/legal handling/cost, без prohibited circumvention. Но **preflight, VPS access и tests в Stage 0C-3 не разрешены**. Документационные GitHub операции этого задания не объявляются готовностью production integrations.

## Scope и зависимости

Все controls уточняют будущую разрешённую реализацию, не разрешают её. Dependency impact (DERIVED):

- G1/G2: data/environment/policy boundaries, versioned action и concurrency/finance accounting до выдачи actual permissions или резерва (H-F01,H-F02,H-F04,H-F07,H-F10,H-F12).
- G3: limits/capabilities/leases, outage/recovery/reconciliation до продолжения внешнего job (H-E04,H-E05,H-F05,H-F08,H-F11,H-F15).
- G4/G5: health freshness, alerts/cards/evidence и risk-appropriate tests до заявления completion (H-E01–H-E03,H-E07,H-E10–H-E13,H-F06,H-F09).
- G6: protected offsite/tested restore/independent emergency/provenance/preflight до отдельно разрешённого production (H-E06,H-E09,H-F03,H-F13,H-F14,H-F16).
- G7: business health sources и applicable data review перед отдельным подключением внешнего проекта (H-E01,H-F02; R46,R47).

H-F14 preflight gate применяется до любого future server deployment/production независимо от G-пакета, а не откладывается только на G6. В этом этапе он не выполняется.

Это не полноценный implementation plan и не автоматическое включение business analytics/new monitoring features в MVP. Сохраняются один тестовый исполнитель, запрет complex multi-agent planning/trading/autonomous real CRM в MVP, независимость Capital Lab/CRM кондитерской и PAUSED автосервиса.

[Статус VPS](../../architecture/INFRASTRUCTURE_STATUS.md) byte-identical: purchased по сообщению владельца, console impairment reported, readiness unverified. Планируемые recovery/preflight не доказательство настроенной инфраструктуры. Неопределённости — [U3-01–U3-16](CONFLICTS_AND_UNCERTAINTIES.md); 0C-4 не начинается.
