# Источник Stage 0C-2 — Project Management & Autonomous Development

Источник SRC-0C2: сообщение владельца «AI Command Center — Stage 0C-2 / Historical Architecture Recovery: Project Management & Autonomous Development» в текущей сессии. Формулировки ниже сохранены из предоставленной сейчас owner-approved historical architecture summary, не из оригинальной стенограммы прежних сессий. Исторические даты, timestamps, approvals, альтернативы и доказательства реализации не предоставлены; дата импорта не является датой исторического решения.

Класс всех 26 пунктов: OWNER_APPROVED_SUMMARY. Сопоставления/влияние/предлагаемые проверки — DERIVED, неизвестные детали — OPEN, непроверенные допущения — ASSUMPTION, несовместимые подтверждённые решения — CONFLICT. Подтверждённые решения владельца имеют приоритет над производными допущениями. Подтверждённый конфликт передаётся владельцу, не разрешается агентом.

**Адресация:** Package D использует supplied IDs H-C01–H-C13, Package E — H-D01–H-D13. Эти ID предоставлены владельцем именно в текущей сводке; они не объявляются исходными ID древних сессий. Не переименовывать их по буквам пакета. Предыдущий Package C из 0C-1 — операционный статус VPS (OPS-C01–OPS-C05), не набор H-C и не архитектурное решение.

База: `docs/stage-0c-1-historical-foundation`, коммит `301b07de174ad0da049813a24ede64dc3f4a04d0`. Рабочая ветка по заданию: `docs/stage-0c-2-projects-development`. Прочитать AGENTS.md, все документы 0A/0B и полный 0C-1; сохранить H-A/H-B, R01–R51, D01–D30 и provenance. Не изменять main и не объединять PR #2/#3. Только documentation-only PR; остановиться после 0C-2, не начинать 0C-3 или реализацию без нового явного задания.

## Package D — Multi-project management (13 decisions)

<a id="h-c01"></a>

H-C01. Support multiple concurrent projects with bounded parallelism and one clearly identified primary priority. The auto-repair CRM project remains PAUSED.

<a id="h-c02"></a>

H-C02. An AI project manager maintains roadmaps, task decomposition, dependencies, milestones, risks, and acceptance criteria.

<a id="h-c03"></a>

H-C03. Maintain living, versioned project knowledge connected to approved requirements, decisions, source materials, and current implementation evidence.

<a id="h-c04"></a>

H-C04. Determine task readiness from actual prerequisites, approvals, dependencies, and evidence, rather than from an AI agent’s confidence alone.

<a id="h-c05"></a>

H-C05. Permit bounded autonomous correction of safe, reversible problems without relaxing approved requirements, tests, budgets, or permissions.

<a id="h-c06"></a>

H-C06. After crashes, restarts, provider failures, or uncertain execution outcomes, reconcile durable state with real external state before continuing or retrying.

<a id="h-c07"></a>

H-C07. Represent project dependencies as a graph; block dependent work when required predecessors are incomplete, invalidated, or unverified.

<a id="h-c08"></a>

H-C08. Verified critical incidents may justify proposing or applying permitted priority changes within approved incident policy. Ordinary AI preferences cannot silently replace owner priorities.

<a id="h-c09"></a>

H-C09. Apply risk-based approvals: routine safe actions within granted authority may proceed, while dangerous, irreversible, externally consequential, or production actions require exact owner consent.

<a id="h-c10"></a>

H-C10. Present owner approvals as explicit interactive cards identifying the action, scope, risk, expected effects, relevant versions, and expiry.

<a id="h-c11"></a>

H-C11. Choose AI models and providers according to required quality, capability, safety, cost, and availability, within confirmed provider permissions and spending limits.

<a id="h-c12"></a>

H-C12. Apply tiered acceptance: automated checks for low-risk results, independent review for significant changes, and owner acceptance for key milestones, MVP, and production.

<a id="h-c13"></a>

H-C13. Handle requirement changes through controlled impact analysis, versioning, dependency updates, and owner approval when approved scope or architecture changes materially.

## Package E — Autonomous coding and agents (13 decisions)

<a id="h-d01"></a>

H-D01. Use a hybrid execution model: a persistent control-plane VPS and on-demand external cloud coding agents, including Codex when authorized and available.

<a id="h-d02"></a>

H-D02. Define a provider-neutral agent adapter interface; do not assume all providers support the same resume, stop, event, or artifact capabilities.

<a id="h-d03"></a>

H-D03. Isolate agent work using dedicated Git branches/worktrees and scoped execution environments, with explicit file, API, network, and credential boundaries.

<a id="h-d04"></a>

H-D04. Require layered verification of generated changes: appropriate static checks, unit, integration, contract, end-to-end, and security tests according to risk.

<a id="h-d05"></a>

H-D05. Use independent AI code review for significant changes as an additional control, never as a replacement for deterministic tests or owner approvals.

<a id="h-d06"></a>

H-D06. Resolve disagreements between agents or reviewers through bounded verification and escalation. No endless debate loops or self-authorized changes to safety limits.

<a id="h-d07"></a>

H-D07. Permit bounded self-repair after failures, but never weaken acceptance criteria, remove failing tests to claim success, or bypass required approvals.

<a id="h-d08"></a>

H-D08. Persist checkpoints, execution history, artifacts, and status. On interruption, reconcile the actual agent/Git/external state before safe resumption.

<a id="h-d09"></a>

H-D09. Production releases follow an explicit staged process with verified build artifacts, checks, owner approval for the exact release, and post-release health assessment.

<a id="h-d10"></a>

H-D10. Apply least privilege and scoped secrets. Coding agents must not receive unrestricted VPS administration, production databases, cross-project credentials, or unrelated sensitive data.

<a id="h-d11"></a>

H-D11. Enforce supply-chain and artifact-provenance controls, including trusted CI evidence, dependency review, pinned source revisions, and release integrity.

<a id="h-d12"></a>

H-D12. External API integrations require mocks or sandboxes where possible, controlled real-call tests only when explicitly authorized, and safe handling of rate limits, idempotency, and ambiguous outcomes.

<a id="h-d13"></a>

H-D13. Agent handoffs use structured context packages containing the approved task, versions, dependencies, permissions, tests, evidence, unresolved questions, and next safe actions.

## Special constraints — supplied source

<a id="special-constraints"></a>

- The auto-repair CRM project is PAUSED. This package must not reactivate it.
- Capital Lab and the confectionery CRM are separate projects, not internal modules of the AI Command Center.
- No live brokerage trading, customer communications, production deployments, or real business integrations are authorized.
- A VPS has already been purchased, but console access was reported temporarily impaired. Do not access, configure, test, or deploy to it.
- No agent may reinterpret a documentation task as authorization to implement the system.
- Preserve the spending-control requirements. Do not turn a budget ceiling into permission to purchase services.

Дополнительные пределы текущего задания: DOCUMENTATION ONLY; no application development or infrastructure actions authorized. No code, dependencies, infrastructure configuration, deployments, or paid actions. Only documentation files may change. Verify unique 26 H/source links and 26 reconciliation entries, intact earlier 26 H-A/H-B, no weakened constraints and no unapproved mechanisms marked APPROVED. Объяснить file counts разными Git comparison bases. Документальные PR и GitHub-операции репозитория разрешены заданием; реальные бизнес-интеграции не подключаются.

Ожидаемые артефакты: source package, historical register, reconciliation matrix, coverage, conflicts/uncertainties, impact on project management/agent execution/security/MVP/dependencies, handoff for 0C-3. Это второй тематический пакет, не полный исторический реестр 128 пунктов.
