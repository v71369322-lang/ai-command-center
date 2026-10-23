# Матрица зависимостей

Статус: DERIVED; обязательные ограничения взяты из [R](../requirements/REQUIREMENTS_REGISTER.md) и [D](../decisions/DECISION_REGISTER.md). Точные численные пределы и механизмы остаются OPEN. По каждой строке указано, что должно быть готово до безопасной проверки результата.

| Пакет | Требования | Решения | Предшественники | Проверка / доказательство | Этап |
| --- | --- | --- | --- | --- | --- |
| G0 Документальные границы | R49,R50 | D16,D17 | Исходники 0A и U | Только документы; нет ложного исторического покрытия | 0B |
| G1 Контракты и структура | R07,R09,R15,R18,R23,R49 | D02,D03,D06,D09,D16; OPEN D18,D19,D25 | G0; отдельное разрешение реализации | Ревью стека, изоляции данных, версий контрактов и CI | S1 |
| G2 Состояние и допуск | R04,R05,R08,R10,R11,R12,R13,R29,R35,R36,R40,R45 | D02–D05,D13,D15; OPEN D20,D23,D24 | G1 | Журнал и сценарии неверных/устаревших прав; конкурентный бюджет | S2 |
| G3 Исполнение и восстановление | R14,R16,R17,R19,R20,R21,R22,R24,R27,R28,R37,R38 | D05–D11,D13; OPEN D20–D25 | G2; протоколы изоляции/повторов | Ограниченный исполнитель, сбои, сверка, отзыв, лимиты | S3 |
| G4 Каналы и наблюдение | R02,R03,R39,R41,R44 | D01,D11,D13; OPEN D23,D29 | G2; G3 для результата агента | Мобильный UI, Telegram, одинаковая версия, пороги и отказ | S4 |
| G5 Приёмка MVP | R06,R25,R26,R48 | D02,D09,D16; OPEN D29 | G3,G4 | Сквозной протокол с фактическим артефактом и независимой проверкой | S5 |
| G6 Эксплуатационная готовность | R01,R30,R31,R32,R33,R34,R51 | D01,D11,D12,D30; OPEN D26,D27 | G5; отдельное разрешение среды и расходов | Отказ центра, восстановление копии, происхождение сборки, совместимость отката | S6 |
| G7 Интеграции и аналитика | R42,R43,R46,R47 | D14,D15; OPEN D28 | G6; разрешение на каждый проект | Контракт, изоляция, происхождение метрик, отсутствие запретных действий | POST |

Это матрица пакетов, а не замена построчным зависимостям R. Каждый R покрыт пакетом. D18–D29 блокируют соответствующую реализацию до ответа владельца; предложенные проверки в R детализируются до начала исполнения. POST не является автоматическим продолжением MVP.

Критический порядок: G0 → G1 → G2 → G3 → G4 → G5 → G6. Проектирование UI возможно после G2, но сквозная приёмка требует G3. Независимый мониторинг, аварийный доступ, копии и происхождение артефактов должны быть проверены до production, даже если сквозной тест уже успешен.

## Дополнение Stage 0C-2: readiness, execution и evidence

Источник — [SRC-0C2](../history/stage-0c-2/SOURCE_PACKAGE.md); связи ниже — DERIVED. Старые G1–G7 не изменены. H-C07 утверждает граф проектных зависимостей, но G-матрица поставки не является его реализацией.

| Зависимая область | Нормативная предпосылка H | Что требуется до дальнейшего безопасного шага |
| --- | --- | --- |
| Запуск/перепланирование | H-C01,H-C04,H-C07,H-C08,H-C13 | Actual readiness, valid approvals/evidence и predecessors; invalidation блокирует downstream; priority exceptions только в incident policy |
| Платный provider dispatch | H-C11,H-D02; R35–R40 | Подтверждённые permissions/capabilities и допустимый резерв/лимит; availability не разрешает покупку |
| Resume/retry/handoff | H-C06,H-D06,H-D07,H-D08,H-D13 | Durable history и сверка agent/Git/external state; bounded verification/escalation и context package без расширения прав |
| Приёмка significant change/MVP | H-C12,H-D04,H-D05 | Risk-appropriate deterministic checks плюс independent AI review significant; owner acceptance key milestone/MVP |
| Выпуск | H-D09,H-D11; R34 | Pinned revision, dependency review, trusted CI/build evidence, exact release consent, health и безопасная совместимость rollback |
| Внешний API | H-D12; R46,R47 | Mocks/sandboxes where possible, отдельное real-call permission, rate limits/idempotency/reconciliation; пауза автосервиса сохраняется |

[Полная сверка](../history/stage-0c-2/RECONCILIATION_MATRIX.md) охватывает все 26 пунктов, [impact](../history/stage-0c-2/IMPACT_REPORT.md) сопоставляет их с G1–G7. Никакой порядок этой таблицы не является разрешением S1–S6, real integrations или кода Stage 0C-2.

## Дополнение Stage 0C-3: safety/recovery gates

Нормы [SRC-0C3](../history/stage-0c-3/SOURCE_PACKAGE.md), ссылки [матрицы](../history/stage-0c-3/RECONCILIATION_MATRIX.md); эта группировка DERIVED, старые G1–G7 сохранены.

| Перед чем | Нормативная зависимость H | Блокирующее условие / evidence |
| --- | --- | --- |
| Paid dispatch/fallback | H-E08,H-F01,H-F05 | Confirmed rights/data/budget, actual/reserved/forecast/delayed/unconfirmed accounting и essential protection; новые commitments требуют owner approval, ceiling не разрешение покупки |
| Dangerous action/restore/resume | H-E04,H-E06,H-F03,H-F04,H-F07,H-F13 | Actual deterministic permission и exact current approval; unknown action blocked, prod restore/dangerous resume после compromise не автоматические |
| Retry/continue/parallel write | H-E05,H-F08,H-F11,H-F12,H-F15 | Bounded controls, operation IDs/journal, revalidate versions, locks/equivalent concurrency/fencing where appropriate; unresolved dangerous effect блокирует dependents |
| Completion/health report | H-E01–H-E03,H-E07,H-E10,H-E12,H-E13,H-F09 | Source/freshness/confidence/impact, no business-symptom = infra-outage shortcut, no agent-only completion |
| Real-data flow | H-F02,H-F06,H-F10 | Applicable localization/legal/log/backup/task/API/transfer review и exact approval; synthetic default, no actual customer data в этом этапе |
| Любой future server deployment/production use | H-F14,H-F16 | Separately authorized required-provider preflight/region/terms/data/cost и exact source/dependency/artifact evidence; preflight gate не откладывается только на G6 |
| Operational recovery readiness | H-E06,H-E09,H-E11,H-F03,H-F05,H-F13 | Independent watchdog/alerts/console path, protected offsite logs/backups, tested restore evidence, authorized containment и independent controls during AI outage |

Ни gate, ни слово tested не означают выполненную проверку. Все runtime/preflight/recovery/paid actions запрещены текущим заданием. Detailed mechanisms/численные лимиты — [OPEN U3](../history/stage-0c-3/CONFLICTS_AND_UNCERTAINTIES.md); [impact](../history/stage-0c-3/SECURITY_AND_RECOVERY_IMPACT.md) сохраняет R34 и scope MVP. Permanent second VPS не default dependency.

## Дополнение Stage 0C-4: KPI, плановые ресурсы и pilot gates

Нормы [SRC-0C4](../history/stage-0c-4/SOURCE_PACKAGE.md), [матрица](../history/stage-0c-4/RECONCILIATION_MATRIX.md); связи ниже DERIVED. Старые G1–G7 сохранены, это не разрешение их реализовать.

| До будущего шага | Source-backed предпосылка | Что нельзя подменить предположением |
| --- | --- | --- |
| KPI computation/report | H-G01–H-G06,H-G09–H-G12 | Owner-approved definitions/source/freshness/joins/reconciliation/accounting/privacy; Ytimes/storefront transactions не double count, uncertain identity не verified |
| Initiative/action proposal | H-G07,H-G08,H-G13 | Hypothesis/baseline/effect/uncertainty и ranking не дают owner consent на spend/outreach/production |
| Server deployment | H-H01–H-H05,H-H07,H-H13 + H-F14 | Approved plan/pins/cost/least privilege/separation и отдельно authorized preflight перед любым deployment, не current purchased readiness |
| Recovery/release | H-H06,H-H09,H-H10 | Provisional RPO/RTO feasibility, integrity/drills/exact artifact/owner approval/health/compatible rollback; no auto-reverse irreversible migrations |
| Agent dispatch/capacity | H-H08; R35–R40/H-F15 | Scope/time/cost/concurrency/cleanup/actual state; permanent extra capacity и commitments owner-approved |
| Real project/data pilot | H-H11,H-H12 + H-F02/H-D12 | Synthetic initial validation, отдельное secured pilot/data/API permission; не inherited authority из analytics report |

FirstVDS planning context не подтверждает actual provider/resources/price. WAL/PITR where feasible не доказательство восстановления, broker/equivalent не выбранный service. [Impact](../history/stage-0c-4/ANALYTICS_AND_INFRASTRUCTURE_IMPACT.md) и [OPEN U4](../history/stage-0c-4/CONFLICTS_AND_UNCERTAINTIES.md) раскрывают недостающие contracts/evidence. Stage 0C-4 запрещает server/preflight/paid/real integration действия.

## Stage 0C-5: vertical slices и дифференцированные gates

[H-I01/H-I03/H-I20/H-I28/H-I29/H-J01](../history/stage-0c-5/SOURCE_PACKAGE.md) уточняют план: short vertical validation, failed acceptance/critical failures block dependents, final MVP требует полного evidence. Старые G1–G7 — DERIVED capability dependencies, не требование сначала закончить отдельные крупные subsystems.

| Future boundary | Canonical outstanding item | Необходимая граница |
| --- | --- | --- |
| Authorization первого implementation scope | CB01 | Owner выбирает exact scope/acceptance/permissions; отдельная programming authorization, не текущий documentation task |
| Local persistent contracts/slice | SG01 | Concrete pins/schema/OpenAPI/events/operation-reconciliation; PG durable authority/Redis transport, Git docs links |
| Actual owner channels/critical action | SG02 | Web MFA/Telegram binding/step-up/current exact approval/default deny |
| Live executor/paid dispatch/cancel | SG03,SG04,SG08 | Provider capabilities/isolation/temporary credentials/evidence preservation/leases/budgets/protected essentials/kill boundaries |
| Final MVP/production | SG05,SG06 | Restore/fault/security/budget/monitoring/runbook/provenance evidence; owner acceptance и exact go-live/release; H-F14 before any server deployment |
| Real read-only pilot/expansion | SG07 | Separate owner project/data/API permission, predefined success metrics, no unauthorized actions/leaks/breaches/critical failures |

[Ledger](../history/stage-0c-5/CONFLICTS_AND_UNCERTAINTIES.md) классифицирует все D18–D29 без изменения OPEN статуса. Global блокировка первого separately authorized offline slice вопросами actual VPS/pilot matching rules не следует из approved norms. [F1–F6 proposal](../history/stage-0c-5/MASTER_PLAN_IMPACT.md) DERIVED и не начат; fixture-only F1 не final MVP.

Unrestored VPS access ME02 не блокирует проектирование/код future local synthetic task при separate grant, но server/preflight/production остаются запрещёнными до своих gates. Никаких dependency/service/container/code actions в текущем этапе нет.
