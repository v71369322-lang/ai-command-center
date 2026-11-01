# Влияние Business Analytics & Infrastructure

Source-backed нормы: [SRC-0C4](SOURCE_PACKAGE.md), [26 records](HISTORICAL_DECISION_REGISTER.md) OWNER_APPROVED_SUMMARY и отдельные section-2 constraints. Все связи, группировки, последствия и предлагаемые будущие проверки этого отчёта — **DERIVED**, не выбранные implementation mechanisms и не результаты тестов.

## Аналитика: evidence, KPI и интерпретации

| Область | Source / прежние связи | Обязательная граница | Будущая проверка / OPEN |
| --- | --- | --- | --- |
| KPI facts vs AI inference | H-G01,H-G05; R43; H-E01,H-E07,H-E10 | Verified fact отдельно от hypothesis/interpretation/recommendation; correlation/plausible factor не proven causal effect | У каждого измеренного значения authoritative evidence; explanation без evidence не выдаётся за измерение или causal proof; U4-02/U4-04 |
| Provenance/KPI dictionary | H-G02,H-G03; H-A09,H-C03,H-C13 | Authoritative source per metric, owner-approved versioned formula/filter/attribution/period/freshness; no invalid joins/duplicates/double count | Изменённая KPI version явно отличается; stale/missing sources раскрыты; U4-02/U4-03 |
| Forecasting/evaluation | H-G06,H-G08; H-A12,H-E07 | Base/optimistic/pessimistic scenarios, uncertainty ranges, backtesting; initiatives с predefined hypothesis/effect/baseline/control or comparison where feasible | Forecast не measured fact, model accuracy не обещана; methodology/horizons/metrics/feasibility OPEN U4-04/U4-05 |
| Finance and unit economics | H-G09; R42,R43 | Revenue/expenses/contribution margins/costs/profit по согласованным accounting definitions и reconciled data | Не вводить произвольные profit/margin formulas; бизнес-отчётность не control-plane spending ledger; U4-06 |
| Customers/cohorts | H-G10; H-F02,H-F06,H-F10 | Cohort/retention/CLV/identity reconciliation в lawful/privacy scope; uncertain matching не verified | Не делать неподтверждённый identity merge/точную CLV по ненадёжным identities; U4-07 |
| Marketing | H-G11; R45; H-A06 | Acquisition cost/ROMI/attribution/channel performance с disclosure missing/unreliable sources | Анализ не разрешает campaigns/spend/outreach/VK API; formulas/source completeness OPEN U4-08 |

Перечислены capabilities, а не готовые business KPI values, formulas или схемы данных. Нет выбора forecast model, causal identification method, attribution model, CLV/CAC/ROMI formula, warehouse/BI product или новых infrastructure services. Конкретизация требует источников, owner-approved definitions и отдельного задания, не access к production в этом этапе.

## Ytimes/CRM: явный запрет двойного учёта

[Source section 2 / confectionery note](SOURCE_PACKAGE.md#confectionery-double-counting) уточняет H-G02/H-G09/H-G10/H-H12: offline Ytimes receipts и CRM deals, классифицированные storefront transactions, могут описывать пересекающиеся business events. Их нельзя молча превращать в независимые подтверждённые продажи и удваивать KPI. Uncertain customer identities не становятся verified.

Что **не выбрано**: join keys, matching windows, equality по сумме/дате/телефону, автоматический dedup, blanket исключение всех storefront deals, назначение одного источника всегда главным, identity-merge algorithm. Даже предположение о тождестве двух конкретных записей требует evidence; реальные записи не получены и не читаются.

Предлагаемый будущий проверяемый результат (DERIVED): isolated synthetic overlap/duplicate/uncertain-identity cases не выдают double-counted или unverified KPI как measured fact; missing/unreliable reconciliation раскрывается. Это критерий проверки принципа, не утверждённый matching protocol. U4-03 требует separate source contract/owner definitions до real pilot.

Lawful source access, minimization/deidentification, localized processing/transfer review, log/backup/task handling и actual permissions H-F02/H-F04/H-F06/H-F10 сохраняются. Нельзя обойти privacy, дав «analytics» роль неограниченного доступа или открытые drill-down links к customer records.

## Отчёты, рекомендации и полномочия

H-G04/H-G12: адаптивные analytical reports через shared mobile-first web/Telegram, daily times **08:00/14:00/21:00 local**, с drill-down к supporting evidence/authoritative records в разрешённом scope. H-B03 quiet hours 23:00–08:00, H-B04 configurable delivery, H-E02/H-E03 dedup/critical exceptions сохраняются. Timezone и правила доставки на границе 08:00 не изобретаются.

H-G07/H-G13: recommendation → proposed structured task, ranked по expected effect/urgency/risk/cost/confidence. Ranking не заменяет primary priority владельца, scope или exact approvals. Ни positive ROI, ни analytical confidence не разрешают customer outreach, marketing expense, financial action, production change или реальную business integration.

Будущая проверка (DERIVED): карточка рекомендации/ссылка на evidence не является permission token; попытка выполнить action без required approval блокируется actual deterministic policy H-A07/H-F04. Algorithm ranking/scoring weights и recommendation UX не выбраны.

## Infrastructure planning vs operational status

| Тема | Source-backed план/норма | Факт о купленном VPS |
| --- | --- | --- |
| Control-plane hosting | H-H01: постоянно доступный VPS для Telegram/web/API-orchestration/state/queue, on-demand isolated agents, home PC не runtime dependency | Не проверено, что это развёрнуто |
| Sizing/provider context | H-H02: приблизительно 2–4 vCPU, 4–8 GB RAM, SSD; FirstVDS Almaty/prices — planning context | Provider/region/plan/spec/storage capacity/current quote/billing неизвестны |
| OS/deployment approach | H-H03/H-H13: Ubuntu LTS, pinned Compose components, modular-monolith stack | Actual OS, release, image/dependency pins, Docker installation и readiness не проверены |
| Hardening | H-H03/H-H05: SSH keys, restricted admin, firewall, HTTPS, MFA where appropriate, updates, least privilege/controlled secrets broker or equivalent | Наличие/настройка controls и credentials не проверены |
| Recovery | H-H06/H-H09: offsite integrity/drills, PG recovery/WAL-PITR where feasible, independent monitoring/emergency/protected recovery | Backups, WAL/PITR, watchdog и actual restore evidence неизвестны |

[OPS-C status](../../architecture/INFRASTRUCTURE_STATUS.md) остаётся отдельным OWNER_REPORTED_OPERATIONAL_STATUS: сервер уже куплен, console access reported temporarily impaired при maintenance; configuration/accessibility/security/readiness/current billing unverified. Не предполагается ни завершение maintenance, ни outage сервера, ни соответствие FirstVDS planning option. Новые source cross-references не меняют operational fact в measured result.

H-H04 сохраняет logical/operational separation от existing CRM/Radmin infrastructure. Capital Lab и CRM не внутренние модули; нет permission менять unrelated servers, переносить CRM на VPS центра или читать их production databases. Топология CRM/Radmin и connection details не выдумываются.

H-H05 broker/equivalent — требование controlled handling, не выбор Vault/cloud service/new standalone microservice. H-H13 запрещает добавлять infrastructure services только ради удобства; необходимость/эквивалентный механизм/architecture change требуют review. H-H09 не требует permanent second VPS автоматически.

## Recovery targets: source-backed, provisional, untested

H-H06 теперь явно даёт **RPO ≤15 минут и RTO ≤4 часов как provisional design targets**, не гарантию и не proven service level. Это новое уточнение current source: старый 0C-3 search по его baseline и conditional references сохраняются исторически корректными. D26/U3-07 теперь имеют target values, но не feasibility/operational evidence.

WAL/PITR — **where feasible**, не обещание уже настроенного PostgreSQL recovery. Offsite backup protection, integrity checks и restoration drills обязательны как будущие controls; retention, locations, measurement scope, workload/resources, procedures и costs ещё OPEN U4-12. Ни benchmark, ни restore drill сейчас не запускается.

Планируемая способность / documented plan / реально проверенное восстановление / production restore — разные уровни evidence. Никакой из них не выводится из покупки сервера или выбора Ubuntu LTS. Production data/DB restore требует exact owner approval (H-E06/H-F03); dangerous resume после compromise — тоже approval (H-F13). H-H10/R34 запрещают автоматически reversing irreversible database migrations.

## Бюджет и жизненный цикл агентов

H-H07 подтверждает hard ceiling **10 000 ₽/month absent explicit owner approval**. R35/D13 «ориентир» — historical wording, актуальная норма H-F01/H-H07 не позволяет silently exceed. Сохраняются R39 warnings и дополнительное source-backed действие: 70% warn, 90% restrict optional, 100% block new nonessential paid work.

Spent/actual, reserved, forecast, delayed charges и прежние unconfirmed costs R36 различаются; billing delay не создаёт free budget. Essential monitoring/security/backups защищаются без silent exceed. Formula accounting/reserves/month boundaries/курсы/тарифы неизвестны; FirstVDS planning context не current cost quote. New commitments даже ниже ceiling, additional permanent capacity H-H08 и существенные architecture changes требуют owner approval.

H-H08: only-as-needed external agents, explicit task scope/time/cost/concurrency/cleanup. Limits не повышаются AI (H-F08); lost-control/provider guarantees H-F15 и reconciliation jobs/costs/permissions сохраняются. Не выбраны cloud provider, численные caps, TTL или cleanup protocol; agents/resources не запускались и не удалялись.

## Release/stack и проверяемая последовательность

H-H10/H-H13 подтверждают Python/FastAPI, React/TypeScript, PostgreSQL, Redis, Python workers, Compose, modular monolith, isolated external execution и versioned interfaces. H-H03 добавляет initial Ubuntu LTS/pinned components. Это не выбор точных versions и не permission создавать сервисы.

Source-backed staged verification/trusted exact artifacts/exact production owner approval/health checks/safe rollback planning действуют с H-D09/H-F07/H-F16. H-F14 preflight требуется перед **любым future server deployment/production**, но в текущем этапе запрещён. No prohibited circumvention, никакой проверки provider/API terms/access или VPS сейчас.

Предлагаемые dependency gates (DERIVED):

| До чего | Необходимая связь | Что остаётся OPEN |
| --- | --- | --- |
| Future metric computation | H-G01–H-G03,H-G09–H-G11: versioned definitions/authoritative lawful sources/reconciliation | Formulas, keys, accounting, identity, source completeness |
| Future initiative recommendation/action | H-G05–H-G08,H-G13: evidence/hypothesis/baseline/uncertainty + owner scope/permissions | Evaluation methods, ranking, acceptance; action без approval не разрешён |
| Future server deployment | H-H01–H-H05,H-H07,H-H13 + H-F14 | Actual spec/OS/access/security/billing, approved plan/pins, separately authorized preflight/resources |
| Future release/recovery | H-H06,H-H09,H-H10 | Feasibility RPO/RTO, tested restore/provenance/health/rollback и exact owner approval |
| Future real-project pilot | H-H11,H-H12 + H-F02/H-D12 | Separate permission, secured project/data/API contracts и real-call test approval |

Это не разрешённый implementation plan S1–S6. Full analytics остаётся future scope за пределами MVP R49; новое чтение source не включает BI, cohorts, marketing или real CRM/brokerage в MVP. One test executor и все security limits сохраняются.

H-H11 теперь прямо утверждает **starting validation with isolated synthetic E2E**. Этот owner-backed pattern не нужно называть Codex assumption; но конкретный A01 synthetic scenario/coverage/acceptance не признан достаточным доказательством готовности MVP. Real projects/data — только отдельно authorized secured pilot stages.

H-H12/SRC-0C4 section 2: Capital Lab и confectionery CRM потенциальные отдельные future pilots; автосервис PAUSED. Ytimes/Bitrix24/VK/T-Invest/brokerage/customer/other production data не подключаются. Нет autonomous live trading, customer outreach, real business production modifications, application work, server access, контейнеров или paid actions. 0C-5 не начинается.
