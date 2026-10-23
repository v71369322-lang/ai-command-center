# Конфликты и неопределённости Stage 0C-4

Source-backed нормы — [SRC-0C4](SOURCE_PACKAGE.md) / OWNER_APPROVED_SUMMARY. Все отношения и разбор этого отчёта DERIVED. База `ef2ed801cc5760e9a700567958e5b8f1f9d2f863`.

## CONFLICT

**0 подтверждённых конфликтов** по доступному контексту. Это не утверждение об отсутствии конфликтов в недоступных оригинальных сессиях. OPEN detail, новое уточнение и planning-vs-fact различие не считаются несовместимыми approved нормами.

| Возможное расхождение | Разбор и source-backed уточнение | Что сохраняется |
| --- | --- | --- |
| R35/D13 «ориентир» vs H-F01/H-H07 hard ceiling | Уже 0C-3 явно уточнил ceiling; 0C-4 подтверждает ту же норму | Исторические строки не меняются, актуальное правило ≤10 000 ₽/month absent explicit approval; commitments ниже потолка тоже не разрешены автоматически |
| Прежний OPEN RPO/RTO и H-H06 explicit provisional targets | В 0C-3 baseline search относился к 0C-2; тогда текущий source имел лишь conditional safeguard. H-H06 теперь даёт explicit provisional ≤15min/≤4h | Старые результаты search не исправляются задним числом. Target values известны, feasibility/performance/measurement OPEN, не новый SLA |
| D18/D26 open versions/sizing и H-H02/H-H03 initial approach | Открытый вопрос не запрещает новому owner source задать planning target/OS family | Ubuntu LTS/approximate sizing source-backed как plan; concrete release/pins/resources/readiness не установлены |
| OPS-C и FirstVDS/Ubuntu planning | Факт покупки не идентифицирует provider/region/plan/OS и не доказывает deployment | OPS-C rows сохранены; новое plan/source cross-reference не превращено в operational verification |
| H-H05 secrets broker/equivalent vs H-H13 no convenient extra services | Approved controlled mechanism не выбирает конкретный product или standalone service | Оба ограничения действуют, implementation choice OPEN; новый microservice не развёртывается |
| H-G analytics и R49 MVP exclusions | Владелец прямо обозначил future capabilities, не новое разрешение полноценной analytics в MVP | Полноценная analytics остаётся вне MVP, pilots отдельные, security обязательна |
| H-H11 synthetic E2E и A01 | Новый source утверждает initial validation pattern, но не достаточность конкретного теста или всего MVP | A01 historical ASSUMPTION остаётся, approved starting pattern не понижается до предположения |
| H-G10 identity reconciliation и privacy/uncertain identity | Аналитическая возможность не позволяет представить вероятностный match как verified | Lawful scope и uncertainty сохраняются; matching algorithm/keys не выбраны |
| H-G07/H-G13 recommendations/ranking и owner priorities/approvals | Предложение задачи не действие и не consent; эффект/ROI не дают spend authority | H-A06/H-A07/H-B07/H-C09 действуют, ordinary AI preference не сдвигает owner priorities |
| Ytimes receipts/storefront deals и missing matching rules | Запрет двойного учёта — явное owner constraint, но формула reconciliation не передана | Не выбирать source-of-truth row, blanket exclusion, join/time-window/customer-match правила; U4-03 |

Если появится реальный CONFLICT двух подтверждённых норм: сохранить обе source references, scope/versions, последствия и dependencies, передать владельцу. Не разрешать его односторонне и не объявлять источник недействительным по предположению. Текущий пакет такого выбора не потребовал.

## OPEN

16 групп U4-01–U4-16. Они могут уточнять U/U2/U3, но не суммируются с ними как отдельные исторические решения. Новая нормативная конкретизация не закрывает целиком старые implementation/evidence вопросы.

| ID | Связи | Что известно / чего нет | Ограничение / что передать дальше |
| --- | --- | --- | --- |
| U4-01 | Все 26 H-G/H-H; GAP01–GAP04 | Нет original transcripts/IDs/dates/approval trails/alternatives, полного исторического register и исходного audit. | Принять supplied summary без вымышленных источников/процента покрытия; сохранить прежние records/statuses. |
| U4-02 | H-G01,H-G02,H-G03,H-G09,H-G11; R42,R43; D14,D19,D28 | Нет approved KPI dictionary: formulas/filters/attribution/period/freshness, authoritative sources, keys/units/currencies и версий source contracts. | Имена метрик не задают формулы. Fact/interpretation/recommendation разделяются; missing/stale/unreliable sources раскрываются. |
| U4-03 | H-G02,H-G09,H-G10,H-H12; SRC-0C4 section 2 confectionery note | Не определены правила reconciliation offline Ytimes receipts и CRM storefront deals: event granularity, matching evidence, statuses/corrections и authoritative transaction view. | Не удваивать одну продажу, но и не изобретать equality/blanket exclusions/join keys/time windows. Uncertain identity не verified. Реальные записи не читаются. |
| U4-04 | H-G05,H-G08; H-A08,H-A12,H-C12 | Нет инициатив, approved hypotheses/expected effects/baselines, control/comparison feasibility, causal evidence и criteria для интерпретаций. | Correlation/plausible explanation не causal proof. Будущая evaluation design не разрешает реальный эксперимент/клиентские действия. |
| U4-05 | H-G06; H-E07; D14,D29 | Не заданы forecast horizons/models, uncertainty construction, backtest splits/metrics и observed outcome sources. | Base/optimistic/pessimistic и uncertainty/backtesting source-approved как capabilities; accuracy, модель/порог и прогнозные числа не выдумываются. |
| U4-06 | H-G09; H-G02/H-G03; D14,D28 | Нет consistent business accounting definitions для revenue/expenses/contribution margins/costs/profit и reconciliation protocols. | Не придумывать margin/profit formulas или отождествлять business accounting с Command Center spend ceiling. |
| U4-07 | H-G02,H-G10,H-G12,H-H11; H-F02,H-F06,H-F10; D25,D28 | Не установлены lawful basis/localization/transfer policies, cohort/retention/CLV definitions и identity-matching evidence/privacy controls. | Не считать uncertain customer match verified, не выполнять auto-merge identities. Actual customer data и real pilot connection не разрешены. |
| U4-08 | H-G11; H-G03/H-G07; H-A06 | Не заданы acquisition-cost/ROMI/attribution/channel definitions и completeness/reliability marketing source data. | Missing/unreliable info раскрывать, не заменять AI inference фактом. Нет marketing spend, VK/customer communications или ad-account calls. |
| U4-09 | H-G04,H-G07,H-G12,H-G13; H-B03,H-B04,H-B07,H-B11,H-B12; D23,D29 | Не определены timezone/delivery/batching, drill-down scopes, ranking method/effect-confidence definitions и recommended-task approval UX. | Точные 08:00/14:00/21:00 local и quiet hours 23:00–08:00 сохраняются. Ranking не сдвигает owner priorities, recommendation не consent. |
| U4-10 | H-H01,H-H02,H-H03; OPS-C01–OPS-C05; D18,D26 | Initial sizing приблизительно 2–4 vCPU/4–8 GB/SSD и initial Ubuntu LTS/Compose approach известны; actual purchased provider/region/plan/spec/OS/security/access/readiness/current billing неизвестны. | FirstVDS Almaty/prices только prior planning context без конкретных current quotes; server/preflight/pricing checks запрещены. Не выбирать LTS release/image/pins за владельца. |
| U4-11 | H-H03,H-H04,H-H05,H-H09,H-H13; D21,D25,D26; H-F04 | Не выбраны SSH/admin/firewall/HTTPS/MFA policies, secrets-broker/equivalent implementation, CRM/Radmin separation topology и independent watchdog/recovery placement. | Source-approved security approach не deployed hardening. Нет выбора vendor/new microservice/second VPS solely for convenience, нет unrelated server access. |
| U4-12 | H-H06; R31,R32,R34; D26,D27; 0C-3 U3-07 | Explicit provisional targets RPO≤15min/RTO≤4h теперь даны; feasibility, measurement scope, WAL/PITR applicability, backup integrity/drills/offsite protection/retention и фактические results неизвестны. | Ранее 0C-3 сохранял условное упоминание и свой baseline search; не переписывать историю. Теперь norm source-backed provisional, не guarantee/SLA. Production restore требует approval, irreversible DB auto-rollback запрещён. |
| U4-13 | H-H02,H-H07,H-H08; R35–R40; D24; H-E08,H-F01 | Hard ceiling/пороги утверждены; spending period/курсы/тарифы/actual-reserved-forecast-delayed-unconfirmed accounting/essential reserve/concurrency caps неизвестны; текущий VPS billing не проверен. | Ни sizing, ни positive ROI, ни сумма ниже потолка не разрешают purchase. Additional permanent capacity owner-approved; essential protection без silent exceed. |
| U4-14 | H-G07,H-G13,H-H04,H-H11,H-H12; R45–R49; D15,D28,D29 | Нет конкретных secured pilot scopes/contracts/permissions, real-call tests и acceptance критериев для Capital Lab/CRM кондитерской; PAUSED CRM не активируется. | Analytics future capability и synthetic validation не разрешают Ytimes/Bitrix24/VK/T-Invest/brokerage/customer integration или real production modifications. |
| U4-15 | H-H01,H-H03,H-H08,H-H10,H-H13; D18–D22,D27 | Не выбраны конкретные runtime/dependency/interface versions, pins, cloud-provider lifecycle/cleanup, release/health/rollback protocols и реальные feasibility/preflight results. | Сохранить modular monolith и отсутствие home-PC runtime dependency; exact release owner approval и no irreversible migration auto-reverse. Ни implementation, ни resource cleanup/API calls сейчас нет. |
| U4-16 | H-G03,H-G06,H-G09,H-G10,H-G11,H-H11,H-H12,H-H13; R49; D16,D29 | Нет дальнейшей roadmap allocation будущих analytics/pilot capabilities, конкретного synthetic E2E acceptance и задания 0C-5. | Полноценная analytics остаётся за MVP. H-H11 утверждает starting pattern, не достаточность A01-сценария/полноту MVP. 0C-5/development только следующим explicit instruction. |

## ASSUMPTION и source-backed уточнения

Новых ASSUMPTION — **0**. Approximate sizing/FirstVDS planning context и provisional recovery targets имеют именно supplied status, не замаскированы как verified specs или guarantees. Ubuntu LTS/pinned Compose/security controls — approved initial approach; не считаются Codex selection, но и не подтверждают actual VPS OS/security.

A01 не переписан: H-H11 source-backed утверждает начало с isolated synthetic E2E; конкретные test design/coverage/acceptance ещё OPEN. Старый U3-07/D26 частично уточнён новыми target values, без закрытия feasibility. Старый U3-16 получил тему 0C-4 только в документационном scope; 0C-5 неизвестен.

Original transcripts/approval trails, полный historical register и original audit не получены. Operational facts остаются owner-reported. Actual customer data, integration/preflight/server access и paid actions не выполнялись.
