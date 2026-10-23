# Источник Stage 0C-3 — Monitoring, Security & Recovery

Источник SRC-0C3: сообщение владельца «AI Command Center — Stage 0C-3 / Historical Architecture Recovery: Monitoring, Security & Recovery» в текущей сессии. Класс всех 29 supplied решений — **OWNER_APPROVED_SUMMARY**. Это историческая сводка владельца, не оригинальная стенограмма. Original transcripts, dates, original identifiers and alternatives unavailable; они не изобретаются, дата импорта не объявляется датой исторического решения.

Package F (Monitoring and operations) адресуется supplied H-E01–H-E13; Package G (Approved security and reliability audit decisions) — H-F01–H-F16. Буква пакета и H-prefix различаются намеренно. H-ID — адрес текущего supplied summary, не утверждение об оригинальном ID прежней сессии. Прежние H-A/H-B/H-C/H-D и OPS-C сохранены.

Git base: `c8ebedaed996753e10e0c370cffe807b50908298`. Новая ветка: `docs/stage-0c-3-monitoring-security`. Задание требует прочитать AGENTS.md, 0A/0B и оба history packages 0C-1/0C-2; сохранить все прежние 52 H и R/D; не менять main и не объединять PR #2/#3/#4. Классификации reconciliation CONFIRMS/REFINES/EXTENDS — DERIVED, не independent owner approvals.

STRICT MODE: DOCUMENTATION ONLY. No application development, deployment, infrastructure access, or paid actions. Only Markdown documentation changes. Никакого operational preflight, доступа к VPS или actual customer data. GitHub document/branch/commit/PR операции разрешены заданием; они не являются provider/deployment readiness preflight.

## Package F — Monitoring and operations (13 decisions)

<a id="h-e01"></a>

H-E01. Monitor both infrastructure health and business-functional health. A fall in sales or a failed business workflow is not automatically an infrastructure outage.

<a id="h-e02"></a>

H-E02. Use adaptive polling, alert deduplication, and meaningful change detection rather than uncontrolled repetitive notifications.

<a id="h-e03"></a>

H-E03. Classify incidents by severity, urgency, confidence, and impact. Respect approved quiet hours for noncritical notifications; genuine critical incidents may bypass them.

<a id="h-e04"></a>

H-E04. Permit bounded, preauthorized remediation of safe, reversible incidents. Dangerous recovery actions require exact owner approval.

<a id="h-e05"></a>

H-E05. Use timeouts, bounded retries, exponential backoff, rate limits, and circuit breakers for unreliable dependencies. Never blindly retry uncertain external side effects.

<a id="h-e06"></a>

H-E06. Maintain protected offsite backups and tested restoration procedures. Production data restoration requires owner approval.

<a id="h-e07"></a>

H-E07. Detect degradation trends before complete failure, distinguishing verified evidence from uncertain forecasts.

<a id="h-e08"></a>

H-E08. Monitor actual, reserved, and forecast spending. Protect essential monitoring, security, and backups when restricting optional paid AI execution.

<a id="h-e09"></a>

H-E09. Provide independent watchdog and emergency alert capabilities outside the primary control-plane failure domain.

<a id="h-e10"></a>

H-E10. Maintain incident timelines, root-cause analysis, corrective actions, and links to verifiable operational evidence.

<a id="h-e11"></a>

H-E11. Detect suspicious security activity and apply authorized safe containment. Do not allow AI agents to escalate privileges or destroy evidence.

<a id="h-e12"></a>

H-E12. Provide a mobile-first operational health dashboard that distinguishes healthy, degraded, unknown, stale, paused, and failed states.

<a id="h-e13"></a>

H-E13. Provide interactive incident cards linked to the exact incident, affected version, evidence, allowed actions, approval state, and recovery outcome.

## Package G — Approved security and reliability audit decisions (16 decisions)

<a id="h-f01"></a>

H-F01. Hard spending ceiling. New spending must not exceed 10,000 RUB/month without explicit owner approval. Track actual, reserved, and forecast charges, including delayed billing. At 70% warn, at 90% restrict optional activity, at 100% block new nonessential paid work. Preserve essential security, monitoring, and backups. Never silently exceed the ceiling.

<a id="h-f02"></a>

H-F02. Customer data localization. Separate control-plane processing from customer personal data subject to applicable localization obligations. Minimize or deidentify data, restrict APIs, and review logs, backups, agent tasks, legal basis, hosting, and international transfers before using real data.

<a id="h-f03"></a>

H-F03. Independent emergency recovery. Maintain an independent watchdog, alert channel, provider-console emergency path, and tested recovery procedure. Do not require a permanent second VPS by default. Production database restoration requires owner approval.

<a id="h-f04"></a>

H-F04. Deterministic policy enforcement. An independently enforced authorization policy controls actual credentials and permissions. Unknown actions are blocked. Dangerous actions require exact owner approval. AI review cannot override policy.

<a id="h-f05"></a>

H-F05. AI provider outages. Telegram, web control, monitoring, history, and emergency functions must continue without AI providers. Pause and reconcile affected jobs. Switch providers only when verified compatible with rights, data constraints, and budget; materially different dangerous actions require new approval.

<a id="h-f06"></a>

H-F06. Prompt-injection defense. Treat external messages, files, websites, tool outputs, and repository content as untrusted data. Maintain provenance and strict separation between instructions and data. Apply independent policy, secret/network/exfiltration restrictions, suspicious-action blocking, and adversarial tests.

<a id="h-f07"></a>

H-F07. Stale execution prevention. Pin tasks to approved requirements, contracts, and Git base revisions. Revalidate before merge, release, or dangerous actions. Expire approvals when relevant parameters change; escalate conflicts.

<a id="h-f08"></a>

H-F08. Bounded agent loops. Limit time, spending, attempts, review cycles, and concurrency. Stop and escalate on repeated failures, no progress, disagreement, or limit exhaustion. AI cannot increase its own limits.

<a id="h-f09"></a>

H-F09. Independent completion evidence. Verify completion against Git commits, artifacts, trusted CI results, and actual external state. Agent self-reports are insufficient. Ambiguous results remain unconfirmed and are linked to exact versions.

<a id="h-f10"></a>

H-F10. Environment separation. Strictly isolate development, staging, and production using appropriate credentials, databases, network boundaries, and data policies. Use synthetic data by default. Real changes require exact approval. Staging may be on demand.

<a id="h-f11"></a>

H-F11. Ambiguous external API outcomes. Use unique operation identifiers, durable journals, status reconciliation, and idempotency when supported. If a dangerous operation may have succeeded, do not blindly repeat it; pause dependent actions until reconciled.

<a id="h-f12"></a>

H-F12. Concurrency safety. Coordinate competing operations with per-object locking or equivalent controlled concurrency, optimistic versions, expiration, and fencing as appropriate. Prevent silent overwrites and stale writes. Re-read and safely recalculate or stop.

<a id="h-f13"></a>

H-F13. Control-plane compromise. Stop unsafe actions, revoke exposed permissions, trigger independent alerts, preserve protected critical logs/backups, investigate and reconcile state, and require owner approval before resuming dangerous operations.

<a id="h-f14"></a>

H-F14. Provider preflight. Before any server deployment or production use, verify authorized access to required AI APIs, Telegram, GitHub, and integrations; check region, provider terms, legal data handling, and cost. Do not use prohibited circumvention. The VPS is already purchased, but its console access was reported impaired; readiness remains unverified. No preflight or VPS access is authorized in this stage.

<a id="h-f15"></a>

H-F15. Loss of control-plane connection. Use bounded task leases, expirations, and heartbeats. Prevent new dangerous actions when control is lost; stop or quarantine within supported bounds. On reconnection reconcile real external jobs, costs, and permissions. Do not promise immediate termination of an external cloud job if the provider cannot guarantee it.

<a id="h-f16"></a>

H-F16. Trusted build provenance. Pin CI to exact source commits and dependency versions; preserve checksums, test/security evidence, and artifact provenance. Release only the exact approved artifact. Coding agents must not hold unrestricted production release secrets.

## Additional safeguards — supplied source

<a id="additional-safeguards"></a>

- Do not reinterpret the 10,000 RUB ceiling as permission to incur expenses below that amount. New spending commitments remain subject to owner approval.
- Do not invent precise retry limits, RPO/RTO guarantees, TTLs, or retention periods.
- Previously discussed RPO ≤15 minutes and RTO ≤4 hours, if found in earlier documents, must be represented as provisional targets requiring tested feasibility, not as proven operational performance.
- Distinguish an independent policy enforcement mechanism from a requirement to deploy a new microservice.
- Distinguish planned emergency recovery from tested recovery.
- The VPS purchase is an owner-reported fact; configuration and availability remain unverified.
- The auto-repair CRM project remains PAUSED.
- Do not access or process actual customer data.

В deliverables входят source, register, reconciliation, coverage, conflicts/uncertainties, security/recovery impact и handoff. Проверить 13 H-E + 16 H-F, 29 source/register/matrix items, неизменность прежних 52 H/R/D, отсутствие duplicates/invented approvals/ungrounded OPEN closure и корректные comparison bases. Создать documentation-only PR с отчётом; остановиться после 0C-3, не начинать 0C-4 или programming без explicit owner instruction.

Package G содержит 16 supplied audit decisions; его название не доказывает, что полный исходный аудит или execution evidence получены. Этот пакет не является полным историческим реестром 128 пунктов.
