# Влияние master plan и предложенный порядок дальнейшей работы

Source-backed norms: [31 H-I/H-J](HISTORICAL_DECISION_REGISTER.md), [SRC-0C5](SOURCE_PACKAGE.md). Весь порядок F1–F6, границы предложений, gates и prompt template здесь **DERIVED, FOR FUTURE CONSIDERATION ONLY**. Ни один stage не начат и не авторизован этим документом.

## Архитектура и ответственность

| Область | Новое/уточнённое требование | Что не выбрано |
| --- | --- | --- |
| Delivery/structure | H-I01/H-I04/H-I28: короткие vertical slices, structured monorepo logical areas orchestrator/API/Telegram/web/infra/migrations/tests | Directory paths, сроки/оценки, concrete tooling; это не microservices |
| Durable state | H-I05/H-I06/H-I11: PostgreSQL authority для runtime tasks/runs/approvals/dependencies/audit/journals/evidence; Git для requirements/decisions/contracts/docs; Redis transports work | Schema/transaction/outbox/queue library/locking implementation. Durable queue не означает Redis sole truth или exactly-once external effects |
| Interfaces/context | H-I07/H-I11/H-I19/H-I26: provider scoped start/status/events/artifacts/results/stop/reconcile/capabilities, versioned OpenAPI/queue events, CI compatibility/additive where feasible, context packets | Unsupported resume/cancel нельзя выдумать; конкретные versioning/event/handoff formats ещё SG01/SG03 |
| Owner/security | H-I14/H-I15/H-I17: один owner, extensible RBAC, web MFA, verified Telegram binding, critical step-up, exact params/version/expiry; scoped secrets/proxy where needed/revocation/kill levels | Auth provider/secret product/step-up protocol не выбраны. Brokerage trading credentials coding agents не выдаются |
| Observability/quality | H-I10/H-I13/H-I20/H-I25: trace IDs/logs/metrics/redaction across whole chain, layered/fault-injection/security verification, independent review, bounded repair, debt register | No invented test results, no debt entries до evidence, no endless refactor, critical failures block progression |
| Release/recovery | H-I12/H-I16/H-I23/H-I29: CI/staging/migration-backup-rollback checks, trusted exact release approval, health, tested runbooks/security-cost audit/watchdog/restore/go-live | Provisional RPO≤15min/RTO≤4h не SLA; no irreversible DB auto-reverse, actual server readiness не проверена |

## MVP: полная приёмка, а не один удачный прогон

H-I02 сохраняет минимальный complete control plane: Telegram, mobile-first web, API/orchestration, PG, durable queue, one isolated test AI executor, history, approvals, spend controls, monitoring. Initial real business projects запрещены; полноценная analytics/complex multi-agent planning не добавляются.

H-I03/H-I20/H-I29 задают evidence checklist final MVP acceptance:

| Группа | Проверяемые outcomes в будущей реализации |
| --- | --- |
| Сквозная цепочка | Real approved Telegram path → orchestration → isolated test executor → independently verifiable result, synchronized web state |
| Durability/faults | PG persistence, duplicate/ambiguous effects handling, timeouts/bounded retries/restarts/disconnects/reconciliation; не agent-only success |
| Permissions/owner | Web MFA/verified Telegram binding/step-up as needed, exact approvals/stale rejection, scoped permissions, kill switches и independent significant review |
| Cost/ops | Actual/reserved/forecast/delayed/unconfirmed accounting/ceiling/reserves, monitor/watchdog, backup/recovery evidence, redaction/isolation/security |
| Acceptance | No unresolved critical failures; owner final acceptance, dependent work blocked when acceptance fails |

Полный набор должен иметь versioned tests/artifacts/CI/external-state evidence в applicable scope. R48/S5 happy path, fixture-only F1 и A01 не завершают MVP. Restore/security/budget evidence нельзя вынести за owner final acceptance только потому, что раньше G6 стоял после G5.

## Предложенные slices и gates — не разрешение выполнения

| Proposal | Измеримый результат для будущего review | Dependencies / gates | Что остаётся запрещено в таком ограниченном scope |
| --- | --- | --- | --- |
| F1 — один local synthetic durable slice | Один fixture Telegram request → task/approval decision → PG journal → Redis work reference → deterministic synthetic adapter → artifact verifier → shared web/report projection; restart/stale-approval/duplicate tests | Owner CB01 и separate authorization; SG01 конкретизируется внутри разрешённого design/test scope до зависимого кода; material choices reviewed | No VPS/server/preflight/provider AI/real Telegram/brokerage/customer APIs, no new paid services. Stub не реальный AI executor, fixtures не owner MFA proof и не complete MVP |
| F2 — реальные owner channels и secure control | Verified Telegram binding + web MFA + exact step-up/approval UX, synchronized state, redacted traces | F1 evidence; SG02, applicable SG08; отдельные scopes credentials/real API tests | No business clients/projects; нельзя default-allow unknown actions или отменять security ради demo |
| F3 — один live isolated test executor | Scoped approved provider start/status/events/artifacts/result/stop/reconcile capabilities, limits/lease/cleanup/evidence preservation, protected spend | F2/applicable checks, SG03/SG04/SG08; отдельный provider/payment authorization | No unsupported instant stop/resume, no unrestricted prod/cross-project credentials, no extra permanent capacity по умолчанию |
| F4 — operational readiness и полная MVP acceptance | Fault-injection/security/restore/runbook/watchdog/CI-cost evidence, exact artifact/staging/migration compatibility, owner MVP + separately approved go-live/release/health | SG05/SG06/SG08; H-F14 authorization/preflight before any server deployment; owner acceptance | Нельзя считать purchased VPS ready, RPO/RTO proven по плану или автоматически reverse irreversible migration |
| F5 — отдельный real pilot | Predefined metrics/evidence, read-only start, zero unauthorized actions/leaks/budget breaches/unresolved critical failures, owner accepts results/expansion | Complete MVP, SG07, отдельный project/data/API/operations authorization | Capital Lab только tentative owner choice, CRM кондитерской may follow; автосервис PAUSED, no autonomous real trading |
| F6 — later scoped improvements | Measured safe improvements/debt reduction, compatibility/review/release evidence; analytics/complex orchestration только если явно включены | Новое owner scope, H-I24/H-I25/H-I27/H-I28; relevant gates | Recommendation/positive ROI не authority, feature flags не permission bypass |

Это не обязательные новые официальные stage numbers и не выбранный календарь. Оценочные ranges/confidence H-I28 надо готовить по конкретному scope/resources после owner choice; значений не выдумано. G1–G7 из 0B сохраняются capability dependencies: каждый короткий slice может затрагивать нужную часть нескольких G, без отмены security gates.

## Что может быть сделано без восстановленного VPS access — только после отдельного разрешения

F1 принципиально возможен в изолированном dev workspace: monorepo/contracts/fixtures, local persistent task flow, deterministic adapter, result evidence и negative tests. При необходимости local ephemeral PG/Redis и dev dependencies должны быть **явно включены** в следующее разрешённое задание; здесь они не устанавливаются/не запускаются. Существующая архитектура позволяет это без home PC runtime или provider-console access.

Это не значит, что можно сегодня писать код, что dev services уже выбраны, или что F1 доказывает deployed Telegram/AI/MFA/restore/watchdog. Actual VPS config/security/billing/ready status ME02 и production preflight остаются отдельными gates. No paid commitments или real data для local synthetic proposal.

## Будущий stage-specific Codex prompt — не запускать

После owner выбора CB01 и отдельной authorization можно подготовить версионированное задание по шаблону:

> Scope: только утверждённый вариант F1 и его acceptance. Прочитать AGENTS/source H-I/H-J и текущие R/D/OPS-C; сохранить approved stack, PG authority/Redis transport/default deny/no exactly-once promises. Подготовить concrete version/contracts plan под SG01, выполнить только отдельно разрешённые local code/test/dependency actions. Все данные synthetic, provider/Telegram ports fixture-only. Сохранить evidence/commits/tests/known gaps, не ослаблять tests/limits, significant changes review. No server/preflight/paid/provider/business APIs, secrets или production. При material scope/architecture conflict остановить зависимую работу и спросить владельца один вопрос. Создать обозримый PR без merge и остановиться.

Шаблон — DERIVED content, не действующая инструкция агенту. Реальные exact scope/branch/base/limits/versions/acceptance owner утверждает в следующем задании; ничего из F1 сейчас не выполнено.

## Ограничения бюджета, данных и closure

Hard 10 000 ₽ ceiling/new commitments/70-90-100/essential protection без silent exceed сохраняются. Forecast/delayed/unconfirmed accounting не подменяется произвольной формулой. Data localization/legal/transfer checks, prompt-injection defense, actual credential policy и least privilege действуют во всех slices.

Business analytics future scope, Ytimes receipts/storefront CRM double counting запрещён без invented matching/verified identity; Capital Lab/CRM независимы. OPS-C: purchased/impaired console owner-reported, FirstVDS/Ubuntu/sizing только plans, actual readiness не проверена.

H-J01 позволяет предложить owner review **восстановления available architecture**, не implementation go-ahead. [Final audit](FINAL_ARCHITECTURE_AUDIT.md) и [owner handoff](OWNER_ACCEPTANCE_HANDOFF.md) — результат текущего документационного этапа; далее остановка.
