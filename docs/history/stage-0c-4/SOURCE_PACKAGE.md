# Источник Stage 0C-4 — Business Analytics & Infrastructure

Источник SRC-0C4 — сообщение владельца «AI Command Center — Stage 0C-4 / Historical Architecture Recovery: Business Analytics & Infrastructure» в текущей сессии. Ниже сохранён точный текст supplied summary: Package H → H-G01–H-G13, Package I → H-H01–H-H13. Все 26 классифицированы OWNER_APPROVED_SUMMARY. Это сводка, не original transcript; original IDs/dates/approval trails/alternatives недоступны. H-G/H-H — адреса текущего supplied summary, не вымышленные оригинальные исторические номера.

Git base `ef2ed801cc5760e9a700567958e5b8f1f9d2f863`; branch `docs/stage-0c-4-analytics-infrastructure`. Прочитать AGENTS.md, 0A/0B и все 0C-1/0C-2/0C-3 historical packages. Сохранить 81 прежний H, OPS-C и R01–R51/D01–D30. Не менять main, не объединять PR #2/#3/#4/#5. Reconciliation/implementation interpretations — DERIVED, не independent owner approvals.

STRICT MODE: DOCUMENTATION ONLY. No programming, deployment, infrastructure access, real integrations, or paid actions. Только Markdown; GitHub source/branch/commit/PR операции этого задания не являются deployment preflight или проверкой readiness. Никаких actual customer data, dependencies/containers/server access/resources/purchases.

## Package H — Business analytics (13 decisions)

<a id="h-g01"></a>

H-G01. Distinguish verified KPI facts from analytical hypotheses, interpretations, and recommendations. Never present an AI inference as a measured business fact.

<a id="h-g02"></a>

H-G02. Maintain explicit data provenance and authoritative sources for each metric. Prevent invalid joins, duplicate transactions, and double counting across business systems.

<a id="h-g03"></a>

H-G03. Use owner-approved, versioned KPI definitions, including formulas, filters, attribution rules, time periods, and data freshness requirements.

<a id="h-g04"></a>

H-G04. Provide adaptive analytical reports at the approved daily times of 08:00, 14:00, and 21:00 local time, subject to notification and delivery policies.

<a id="h-g05"></a>

H-G05. Explain observed changes using supporting evidence, separating correlations and plausible factors from proven causal effects.

<a id="h-g06"></a>

H-G06. Support base, optimistic, and pessimistic forecasts, uncertainty ranges, and backtesting against observed outcomes. Do not claim unwarranted prediction accuracy.

<a id="h-g07"></a>

H-G07. Convert analytical recommendations into proposed tasks requiring appropriate authorization. Recommendations do not independently authorize customer outreach, spending, production changes, or external business actions.

<a id="h-g08"></a>

H-G08. Evaluate initiatives against predefined hypotheses, expected effects, baselines, and controls or comparison groups where feasible.

<a id="h-g09"></a>

H-G09. Analyze revenue, expenses, contribution margins, costs, and profit using consistent accounting definitions and reconciled source data.

<a id="h-g10"></a>

H-G10. Support cohort analysis, retention, customer lifetime value, and identity reconciliation while respecting privacy, lawful processing, and uncertainty in customer matching.

<a id="h-g11"></a>

H-G11. Support marketing analysis including acquisition cost, ROMI, attribution, and channel performance, with clear disclosure of missing or unreliable source information.

<a id="h-g12"></a>

H-G12. Present analytics through the shared mobile-first web and Telegram interfaces, with drill-down to evidence and authoritative records.

<a id="h-g13"></a>

H-G13. Rank proposed business decisions by expected effect, urgency, risk, cost, and confidence, while preserving owner priorities and approval boundaries.

## Package I — Infrastructure and deployment architecture (13 decisions)

<a id="h-h01"></a>

H-H01. Use a hybrid architecture with a continuously available VPS for Telegram, web, API/orchestration, persistent state, and queue coordination, plus isolated cloud coding agents launched on demand. The home PC is not a required runtime dependency.

<a id="h-h02"></a>

H-H02. The initial VPS sizing target is approximately 2–4 vCPU, 4–8 GB RAM, and SSD storage. Previously considered FirstVDS Almaty configurations and prices are planning context, not independently verified current infrastructure specifications.

<a id="h-h03"></a>

H-H03. Use Ubuntu LTS and pinned Docker Compose deployment components as the initial infrastructure approach. Apply SSH keys, restricted administrative access, firewall, HTTPS, MFA where appropriate, and security updates.

<a id="h-h04"></a>

H-H04. Keep the AI Command Center VPS logically and operationally separate from the existing CRM/Radmin infrastructure. Do not assume permission to modify unrelated servers.

<a id="h-h05"></a>

H-H05. Use least-privilege credential handling and a controlled secrets broker or equivalent mechanism. Coding agents must not receive unrestricted VPS administration or unrelated production credentials.

<a id="h-h06"></a>

H-H06. Maintain protected offsite backups, PostgreSQL recovery capability including WAL/PITR where feasible, backup integrity checks, and restoration drills. RPO ≤15 minutes and RTO ≤4 hours are provisional design targets, not verified guarantees.

<a id="h-h07"></a>

H-H07. Maintain a hard 10,000 RUB monthly ceiling for new expenses absent explicit owner approval. Track spent, reserved, forecast, and delayed charges. Apply 70% warning, 90% restriction, and 100% blocking of new nonessential paid work, while protecting essential safety functions without silently exceeding the ceiling.

<a id="h-h08"></a>

H-H08. Run external cloud agents only as needed, with explicit task scope, time limits, cost limits, concurrency bounds, and cleanup. Additional permanent capacity requires owner approval.

<a id="h-h09"></a>

H-H09. Use independent monitoring, emergency alerting, and protected recovery mechanisms outside the primary control-plane failure domain; a permanent second VPS is not automatically required.

<a id="h-h10"></a>

H-H10. Release control-plane updates through staged verification, trusted artifacts, exact owner approval for production, health checks, and safe rollback planning. Never automatically reverse irreversible database migrations.

<a id="h-h11"></a>

H-H11. Start validation with isolated synthetic end-to-end scenarios. Real projects and data may be connected only through separately authorized, appropriately secured pilot stages.

<a id="h-h12"></a>

H-H12. Treat Capital Lab and the confectionery CRM as separate potential future pilot systems, not internal modules. The auto-repair CRM remains PAUSED. No autonomous real brokerage trading or business production modifications are authorized.

<a id="h-h13"></a>

H-H13. Preserve the approved modular-monolith stack: Python/FastAPI, React/TypeScript, PostgreSQL, Redis, Python workers, and Docker Compose, with isolated external execution environments and versioned interfaces. Do not introduce additional infrastructure services solely because they are technically convenient.

## Operational status and interpretation — supplied section 2

<a id="operational-status"></a>

The VPS has already been purchased according to the owner. Console access was reported temporarily impaired during provider maintenance. Its exact configuration, accessibility, security posture, deployment readiness, and current billing remain unverified.

<a id="planning-not-purchased-spec"></a>

Do not infer that the purchased VPS necessarily matches the earlier FirstVDS planning option.

<a id="stage-prohibitions"></a>

Do not access the VPS, run preflight checks, create infrastructure resources, or purchase services.

<a id="analytics-access-boundary"></a>

Business analytics requirements describe future capabilities. They do not authorize connecting Ytimes, Bitrix24, VK, T-Invest, brokerage accounts, customer records, or other production data during Stage 0C-4.

<a id="confectionery-double-counting"></a>

For the confectionery CRM, preserve the requirement to avoid double counting offline Ytimes receipts and CRM deals classified as storefront transactions. Do not invent matching rules or treat uncertain customer identities as verified.

Эти пять абзацев section 2 — дополнительные source anchors: они не создают ещё пять H-решений в счётчике 26. Operational сообщения — OWNER_REPORTED_OPERATIONAL_STATUS, не independently verified readiness. Запреты/правило double-counting — явные ограничения владельца, не Codex matching rule.

Задание также требует: отделять future analytics от MVP; сохранять security/owner approval boundaries; hard ceiling не считать permission below ceiling; planning assumptions не приравнивать к purchased VPS facts; provisional RPO/RTO не повышать до proven service levels; lawful data handling и uncertain identity не скрывать. Все 81 H прежних пакетов неизменны. CONFLICT отделять от OPEN details, не выдумывать процент unavailable historical register.

Результат: семь документов пакета, необходимые labeled appendices, source/register/matrix для 13+13, проверки сохранности H/OPS-C/R/D и документационных путей, Git incremental vs cumulative counts, documentation-only PR. После Stage 0C-4 остановиться; 0C-5/software development только по следующему explicit owner instruction.
