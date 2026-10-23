# Источник Stage 0C-5 — Master Plan Recovery & Architecture Reconciliation

SRC-0C5 — сообщение владельца «AI Command Center — Stage 0C-5 / Master Plan Recovery & Architecture Reconciliation». Exact supplied wording ниже — historical summary, не original transcript. Все 30 H-I и 1 H-J: OWNER_APPROVED_SUMMARY. Original IDs/timestamps/quotations/approval evidence/alternatives не предоставлены и не изобретаются. H-I/H-J — supplied identifiers текущего пакета, не утверждение об original session IDs.

Base `f0797055dc04df3ebb3596e87148fad9f7899914`; branch `docs/stage-0c-5-master-plan-audit`. Прочитать AGENTS.md, 0A/0B и все четыре historical packages; сохранить prior 107 H, five OPS-C, R01–R51/D01–D30. Не менять main и не объединять PR #2–#6.

STRICT MODE: DOCUMENTATION AND ARCHITECTURAL AUDIT ONLY. No programming, deployments, server access, operational preflight, paid actions, or production integrations. Repository documentation/branch/commit/PR операции разрешены заданием; они не operational preflight. Никаких dependencies/customer data/real integration/credential-management действий.

## Package J — Master implementation plan (30 decisions)

<a id="h-i01"></a>

H-I01. Organize delivery as short vertical slices with early end-to-end validation rather than disconnected large subsystems.

<a id="h-i02"></a>

H-I02. MVP is the smallest complete control plane: Telegram bot, mobile-first web, orchestrator/API, PostgreSQL, durable queue, one isolated test AI executor, execution history, owner approvals, basic spending controls, and monitoring. Do not connect real business projects in the initial MVP.

<a id="h-i03"></a>

H-I03. MVP acceptance requires verified end-to-end execution from Telegram through orchestration and isolated agent to independently verifiable result, synchronized web state, persistence, errors, timeouts, retries, restart recovery, approvals, permissions, budget enforcement, backup/recovery evidence, and monitoring. Owner performs final acceptance.

<a id="h-i04"></a>

H-I04. Use a structured monorepo with orchestrator, API, Telegram, web, infrastructure, migrations, and tests. Maintain versioned contracts, isolated Git work, protected main, CI, and owner approval of the exact production build.

<a id="h-i05"></a>

H-I05. Use Python/FastAPI, React/TypeScript, PostgreSQL, Redis, Python workers, and Docker Compose in a modular-monolith architecture. PostgreSQL is authoritative; external cloud agents remain isolated.

<a id="h-i06"></a>

H-I06. Persist tasks, approvals, audit records, and execution journals durably in PostgreSQL. Redis transports work but is not the sole source of truth. Use unique operation IDs, leases, crash reconciliation, and no blind retries. Never promise exactly-once external effects.

<a id="h-i07"></a>

H-I07. Define a unified agent-provider interface for scoped start, status, events, artifacts, results, stop, reconciliation, and capability discovery. Do not claim unsupported provider resume or cancellation semantics.

<a id="h-i08"></a>

H-I08. Isolate each agent execution with appropriately scoped environment, Git branch/worktree, filesystem/API/network permissions, temporary credentials, and cleanup. Preserve evidence before disposal. No unrestricted production or cross-project access.

<a id="h-i09"></a>

H-I09. Use adaptive, bounded parallelism based on priority, dependencies, risk, spending, and resources. MVP begins with one executor and preserves resources for monitoring.

<a id="h-i10"></a>

H-I10. Verify AI output using acceptance criteria, Git evidence, lint/type checks, unit/integration/E2E/security tests as appropriate, and independent review for significant changes. Repair attempts are bounded and must not weaken tests.

<a id="h-i11"></a>

H-I11. Store approved architecture decisions, requirements, contracts, and documentation in Git; tasks, runs, approvals, dependencies, and evidence in PostgreSQL. Provide versioned context packets and handoffs. Flag contradictions rather than silently rewriting approvals.

<a id="h-i12"></a>

H-I12. Use development → CI → isolated staging → migration/backup/rollback checks → owner approval for exact release → production → post-release health verification. Application rollback is not equivalent to database rollback.

<a id="h-i13"></a>

H-I13. Maintain structured logs, metrics, and trace IDs across interfaces, API, database, queue, workers, and agents. Track spending, retries, incidents, approvals, recovery, and task progress. Redact sensitive data and provide mobile operational visibility.

<a id="h-i14"></a>

H-I14. MVP has one owner, with extensible role-based access. Secure web access uses MFA; Telegram commands require verified owner binding. Critical actions require appropriate step-up confirmation. Approvals bind exact action, parameters, version, and expiry.

<a id="h-i15"></a>

H-I15. Protect secrets outside Git and ordinary task records. Use least-privilege, scoped, revocable credentials and controlled API proxying where necessary. Support rotation and emergency revocation. Coding agents must not receive real brokerage trading credentials.

<a id="h-i16"></a>

H-I16. Maintain protected offsite PostgreSQL backups, WAL/PITR where feasible, configuration and key recovery, integrity checks, and restore drills. RPO ≤15 minutes and RTO ≤4 hours are provisional targets pending validation. Production restoration requires owner approval.

<a id="h-i17"></a>

H-I17. Provide kill switches at task, agent, project, and unsafe-operation levels. Safe cancellation and credential revocation must preserve monitoring, essential backups, and audit evidence. Dangerous resumption requires owner approval.

<a id="h-i18"></a>

H-I18. External API adapters use timeouts, rate limits, bounded backoff, circuit breakers, supported idempotency, and state reconciliation before retrying uncertain effects.

<a id="h-i19"></a>

H-I19. Use versioned OpenAPI and queue event contracts, compatibility checks in CI, additive evolution where feasible, and staged migrations. Do not break active consumers or in-flight tasks silently.

<a id="h-i20"></a>

H-I20. Require unit, contract, integration, E2E, and fault-injection tests covering restarts, duplicate effects, stale approvals, budgets, disconnects, backup restoration, isolation, security, and kill switches. Critical failures block progression.

<a id="h-i21"></a>

H-I21. Pilot first with synthetic data. Later connect an individually owner-approved real project, tentatively Capital Lab, beginning read-only and advancing only through secured approvals. The confectionery CRM may follow. The auto-repair CRM remains PAUSED.

<a id="h-i22"></a>

H-I22. Define pilot success metrics before starting: accepted results, test reliability, execution time, cost, repair effectiveness, recovery, and owner time. Zero unauthorized actions, data leaks, budget breaches, or unresolved critical failures. Owner approves any autonomy expansion.

<a id="h-i23"></a>

H-I23. Operational acceptance requires tested runbooks for emergency stop, restoration, updates, access, and budget management; independent watchdog; backup restore evidence; security and cost audit; and explicit owner go-live approval.

<a id="h-i24"></a>

H-I24. AI may propose self-improvements, but material changes require owner authorization, isolated branches, tests, review, staging, feature flags where appropriate, exact production release approval, and safe rollback planning.

<a id="h-i25"></a>

H-I25. Maintain a technical-debt register with impact, risk, value, and priority. Address critical vulnerabilities promptly while avoiding endless refactoring. Architectural changes require documented decisions and owner approval.

<a id="h-i26"></a>

H-I26. Treat documentation as code: trace requirements → decisions → commits → tests → evidence → documentation. Validate traceability through CI and structured agent handoffs.

<a id="h-i27"></a>

H-I27. Coordinate multi-agent work using dependency graphs, component ownership, isolated branches, versioned interfaces, compatibility checks, integration verification, and coherent release boundaries. Do not introduce complex multi-agent orchestration into MVP by default.

<a id="h-i28"></a>

H-I28. Plan short, adaptive stages with dependencies, measurable outcomes, estimated ranges, and confidence. Recalculate risks and critical paths using verified evidence. Material roadmap changes require owner approval.

<a id="h-i29"></a>

H-I29. Apply tiered acceptance: automated checks for safe low-risk changes, independent review for significant work, owner checkpoints for major milestones, MVP, and every production release. Failed acceptance blocks dependent execution.

<a id="h-i30"></a>

H-I30. Maintain a master requirements, decisions, dependencies, risks, acceptance, and implementation plan, with stage-specific Codex prompts. Initial stages are documentation and audit only. No programming or operational work without separate authorization. The VPS has already been purchased, but that fact does not authorize configuration or deployment.

## Package K — Final architecture closure decision

<a id="h-j01"></a>

H-J01. Before freezing the architecture, audit all available historical decisions for completeness, contradictions, security and budget constraints, MVP boundaries, and implementation dependencies. Escalate only genuine blocking choices to the owner, one question at a time. Architecture restoration may be declared ready for owner review only when critical conflicts are resolved, remaining gaps are explicitly registered, and evidence supports the reconciliation. Programming requires separate explicit owner authorization.

## Reconciliation and audit obligations — current assignment

Source-backed решения отделяются от DERIVED interpretations, ASSUMPTION и OPEN. Planning targets не verified operational facts; architecture restoration не implementation, documentation completion не actual tested functionality; MVP не post-MVP; CONFLICT не missing technical detail; approval to document не spend/deploy/access/develop authority.

Требуется audit всей доступной базы 0A/0B/0C-1–0C-5: 138 supplied H (107+31), source preservation/traceability, approved/derived contradictions, hard budget/permissions, security/localization/secrets/isolation/injection, durability/ambiguous effects/recovery/emergency, MVP, dependencies/sequence и безопасно возможная future работа до восстановления VPS access. Не утверждать exact count original historical decisions или полное original coverage.

Outstanding item classes из задания: CRITICAL_BLOCKER (решить до implementation authorization), STAGE_GATE (до конкретного позднего шага), NONBLOCKING_OPEN, MISSING_EVIDENCE, CONFIRMED_CONFLICT. Only genuine blocking owner choices эскалировать по одному вопросу, не выбирать новые механизмы за владельца и не повышать старые OPEN до approved по общему принципу.

Восемь required files: source, register, matrix, coverage, conflicts/uncertainties, master-plan impact, final audit, Russian owner handoff. Проверить exact 30+1/31 source-register-matrix, prior H/OPS-C/R/D, links/IDs/no exact duplicates, Git comparison counts и documentation-only diff. Создать PR, остановиться и ждать explicit owner review/authorization; programming/operational preflight/следующий этап не начинать.
