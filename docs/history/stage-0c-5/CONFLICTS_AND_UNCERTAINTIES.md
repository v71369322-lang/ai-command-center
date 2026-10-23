# Конфликты и классифицированные outstanding items

Нормы [SRC-0C5](SOURCE_PACKAGE.md) — OWNER_APPROVED_SUMMARY; выводы audit и классификация **DERIVED**, для owner review. Ни один старый OPEN не помечен approved/closed без своего источника и evidence.

## CONFIRMED_CONFLICT

**0 подтверждённых конфликтов** двух несовместимых owner-approved требований по available context. Это не утверждение о недоступной истории.

| Сопоставление | Результат сверки |
| --- | --- |
| PostgreSQL/Redis: B3/B4, R09/R29 vs H-I06 | PG authority не противоречит Redis transport/queue. Durable jobs/journals явно PG; Redis не sole truth, exactly-once внешних effects не обещается |
| Initial MFA where appropriate H-H03 vs web MFA H-I14 | Scope уточнён: secure web MFA обязательно, инфраструктурное where appropriate не исключало это. Concrete MFA/binding method SG02 |
| Full MVP vs G5/G6 split | Owner H-I03 не позволяет final MVP acceptance без failure/backup/recovery/monitoring evidence. Старый split DERIVED, уточнение не owner-owner conflict |
| Hard ceiling vs «ориентир» R35/D13 | H-F01/H-H07 остаются актуальной обязательной границей; commitments не разрешены даже ниже потолка; historical wording сохранён |
| RPO/RTO and purchased VPS | H-H06/H-I16 provisional design targets и Ubuntu/sizing plans не operational facts; OPS-C unchanged |
| H-I21 pilot order vs H-H12 standalone projects | Tentative read-only Capital Lab-first путь условный, не actual authorization. Independent systems/PAUSED CRM сохраняются |
| Safe autonomy vs real changes/step-up | Неоднозначная actual action требует scope/risk policy SG02/SG07, default deny сохраняется; offline fixtures не обходят approvals |
| Broker/equivalent, independent recovery, modular monolith | Ни новый secret microservice, ни permanent second VPS не следуют автоматически из норм |

Если подтвердится несовместимость двух owner-approved норм: сохранить exact sources/versions/scope/dependencies, классифицировать CONFIRMED_CONFLICT и запросить owner choice один вопрос за раз. Здесь не было выбора победившего owner решения.

## Owner-approved vs DERIVED 0B

- **DI01 — A01:** synthetic initial validation теперь approved H-H11/H-I21; A01 о достаточности отдельного теста не evidence final acceptance. H-I03/H-I20/H-I23/H-I29 имеют приоритет. Historical ASSUMPTION сохранён, не owner approval.
- **DI02 — blanket blocking:** derived фраза «D18–D29 блокируют реализацию до ответа владельца» слишком широка при применении ко всем стадиям сразу. H-J01 требует only genuine blocking choices. Статусы OPEN сохранены, их применимость разделена SG01–SG08/NB01–NB03; D28 о real pilots не должен блокировать separately authorized offline synthetic code.
- **DI03 — waterfall interpretation:** G1→G6 из 0B — capability dependencies, не owner-approved необходимость строить крупные disconnected subsystems. H-I01/H-I28 требуют short vertical slices; план уточняется appendices, обязательные safety gates не снимаются.
- **DI04 — happy path ≠ MVP:** S5/E2E criterion R48 не заменяет всю приёмку. H-I03/H-I20/H-I23 явно добавляют persistence/errors/timeouts/retries/restart/approvals/permissions/budget/restore/monitoring и owner acceptance до объявления complete.
- **DI05 — templates vs facts:** proposed thresholds, protocols, tests и readiness labels не executed evidence. H-F09/H-I26 требуют real versioned links; original assumptions не повышают targets до guarantees.

Это исправление derived interpretations, **не CONFIRMED_CONFLICT между владельцами**. Ни одна строка R/D и ни один прежний H не изменены.

## Outstanding ledger

15 нормализованных items: **1 CRITICAL_BLOCKER, 8 STAGE_GATE, 3 NONBLOCKING_OPEN, 3 MISSING_EVIDENCE**, 0 CONFIRMED_CONFLICT. Это не сумма старых U/U2/U3/U4: группы пересекаются и сохраняют historical status.

| ID | Класс | Когда требуется | Источники / прежние вопросы | Outstanding | Решение/ограничение |
| --- | --- | --- | --- | --- | --- |
| CB01 | CRITICAL_BLOCKER | Перед implementation authorization | H-I01,H-I03,H-I28,H-I30,H-J01; U4-16 | Не утверждён точный scope/acceptance/permission envelope следующего implementation задания. F1 ниже — DERIVED предложение, не разрешение. | Owner выбирает/утверждает конкретный первый scope и границы; затем отдельная explicit programming authorization. Это один scope choice, не необходимость решить все technical OPEN сейчас. |
| SG01 | STAGE_GATE | До первого persistent vertical slice / изменения контрактов | D18,D19,D20,D29; H-I04–H-I06,H-I11,H-I19,H-I26 | Concrete runtime pins, schema/module ownership, operation state/reconcile, queue/event/OpenAPI contracts, minimal acceptance и compatibility ещё не выбраны. | В отдельном разрешённом задании подготовить/проверить конкретизацию под fixed architecture; material architecture changes owner-approved. PG authoritative, Redis transport и no exactly-once norm уже утверждены. |
| SG02 | STAGE_GATE | До реального owner web/Telegram и critical actions | D23,D25; H-A07,H-C09,H-I14,H-I15 | Web MFA method, verified owner binding, step-up/risk policy, exact approval identity/expiry/revocation, timezone/delivery и real-change scope. | One-owner MVP/MFA/binding/step-up — обязательные нормы, методы OPEN. Unknown action blocked; fixture auth в F1 не production identity evidence. |
| SG03 | STAGE_GATE | До live cloud executor/provider dispatch | D20–D22,D25; H-I07–H-I09,H-I15,H-I17,H-I18 | Provider/capability/rights/data matrix, isolation/network/temporary credentials, limits/lease/stop guarantees, cleanup и evidence-preservation protocols. | Live API/task только отдельно разрешённые с tested containment, capability reconciliation и preserved evidence before disposal; unsupported stop/resume не обещать. |
| SG04 | STAGE_GATE | До paid execution/new commitments/capacity | D24; R35–R40; H-F01,H-H07,H-I09 | Accounting actual/reserved/forecast/delayed/unconfirmed, тарифы/курсы/period/essential reserve/atomic reservation и actual VPS billing не проверены. | Hard ceiling 10 000 ₽/month + 70/90/100 + protected essentials source-approved; commitments ниже ceiling и extra capacity требуют approval, no silent exceed. |
| SG05 | STAGE_GATE | До final MVP acceptance / restoration / operational go-live | D26,D27,D29; H-I03,H-I16,H-I23 | Offsite protection, PG/config/key recovery, WAL/PITR feasibility, independent watchdog/emergency path, measured restore drills и target feasibility. | Backup/recovery evidence до owner MVP acceptance, не после happy-path pass. Provisional RPO≤15min/RTO≤4h не SLA; prod restore/dangerous resume approval; no default second VPS. |
| SG06 | STAGE_GATE | До stage promotion / server deployment / production release | D18,D27,D29; H-F14,H-I10,H-I12,H-I19,H-I20,H-I23,H-I29 | CI/test/fault-injection/security evidence, compatible migrations, staging, exact artifact provenance, preflight/terms/region/cost, tested runbooks и go-live approval. | Critical failures block progression. Отдельно authorized preflight до любого server deployment, exact release approval + post-health. App rollback не irreversible DB reverse. |
| SG07 | STAGE_GATE | До любого real-project/data pilot / autonomy expansion | D28,D25; R45–R49; H-I21,H-I22 | Owner selection пилота, read-only scope, lawful/localization/source/API controls, real-call permissions, predefined metrics/acceptance и safety evidence. | Capital Lab tentative, не connection permission; CRM может позже, автосервис PAUSED. Zero unauthorized actions/leaks/budget breaches/unresolved critical failures; expansion owner-approved. |
| SG08 | STAGE_GATE | До enabling cancel/unsafe-operation/compromise recovery paths | D21,D23,D25,D26; H-I08,H-I15,H-I17,H-I20,H-I23 | Task/agent/project/operation kill boundaries, credential revoke/rotation, protected monitoring/backups/audit, emergency and dangerous-resume protocol. | Safe cancellation не уничтожает evidence/essential controls; supported external stop bounds проверяются. Unknown/dangerous actions не включать по умолчанию. |
| NB01 | NONBLOCKING_OPEN | После MVP; до scoped analytics work | D14; U4-02–U4-09; H-G01–H-G13 | KPI formulas/accounting/forecasts/causality/identity/marketing/attribution и Ytimes/storefront reconciliation детали. | Не блокируют первый synthetic slice; source-backed prohibition double counting/privacy/matching uncertainty уже действует. До реального использования нужные решения входят в SG07. |
| NB02 | NONBLOCKING_OPEN | По мере появления codebase/расширения orchestration | D19; H-I24,H-I25,H-I27,H-I28 | Detailed debt entries/estimates/critical paths, multi-agent component ownership и advanced role/autonomy expansion не конкретизированы. | Не выдумывать tech debt/оценки/выбор provider; complex multi-agent orchestration не MVP default. Critical vulnerabilities не откладывать, material changes owner-approved. |
| NB03 | NONBLOCKING_OPEN | В будущих assistant feature slices | 0C-1 U04–U06,U09,U12; H-B02,H-B06,H-B08,H-B09 | Voice/attachments/extended knowledge/reminder details и точная phase allocation дополнительных assistant функций. | Не входят автоматически в первый slice; будущая реализация обязана сохранить approved capabilities/privacy. Scope review отдельно, не тихая отмена требований. |
| ME01 | MISSING_EVIDENCE | Историческая полнота | GAP01–GAP04; H-J01 | Original transcripts/IDs/timestamps/approval trails/alternatives/full original register и исходный historical final audit недоступны. | Текущий audit оценивает available summaries, не объявляет exact original count/coverage. Отсутствие transcripts не превращать в запрет принять limited recovered baseline. |
| ME02 | MISSING_EVIDENCE | Фактическая эксплуатационная готовность | OPS-C01–OPS-C05; H-F14,H-H02,H-H03,H-I30 | VPS provider/region/spec/OS/access/security/billing/readiness и независимая recovery infrastructure не проверены. | Purchased/impaired console owner-reported; не infer FirstVDS match, доступ не проверять. Evidence обязателен у SG05/SG06, не prerequisite для authorization offline F1. |
| ME03 | MISSING_EVIDENCE | Фактическая работоспособность | H-A12,H-F09,H-I03,H-I20,H-I23 | Нет реализации/CI/security/fault-injection/restore/integration/MVP acceptance evidence. В этом задании проверяется только документация. | Это не failed tests и не evidence functionality. Будущие checks у SG05/SG06; нельзя требовать готовую систему до authorization её разработки. |

CB01 — owner choice точного следующего scope, не новый технический конфликт. Отдельная explicit programming authorization остаётся обязательной после review/утверждения задания. Владелец не обязан сейчас лично выбирать каждую queue/auth/library/pilot деталь; конкретизация у своего gate в будущем authorized scope, material architectural choices эскалируются.

## Сопоставление старых OPEN без закрытия

| Старые записи | Текущий применимый item |
| --- | --- |
| D18 | SG01,SG06 |
| D19 | SG01,NB02 |
| D20 | SG01,SG03 |
| D21 | SG03,SG08 |
| D22 | SG03 |
| D23 | SG02,SG08 |
| D24 | SG04 |
| D25 | SG02,SG03,SG05,SG07,SG08 |
| D26 | SG05,SG06,ME02 |
| D27 | SG05,SG06 |
| D28 | SG07,NB01 |
| D29 | CB01,SG01,SG05,SG06,ME03 |

Старые U по sources/audit → ME01; VPS/feasibility → ME02/SG05/SG06; budgets → SG04; provider/isolation/loops/handoff → SG01/SG03/SG08; identity/approvals/quiet-time delivery → SG02; analytics/customer/pilots → NB01/SG07; actual tests/A01 → ME03. Новые known high-level нормы PG authority, MFA, synthetic starting pattern и provisional targets не закрывают concrete implementation/evidence.

Новых ASSUMPTION — 0. Decision timestamps/approval trails/actual operational evidence не придуманы. Цель 0C-5 — documentation ready for owner review; implementation и freeze не разрешены.
