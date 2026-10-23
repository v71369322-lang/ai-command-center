# Источник пакета Stage 0C-1

Локальный идентификатор источника: SRC-0C1. Источник — сообщение владельца «AI Command Center — Stage 0C-1 / Historical Architecture Recovery: Foundation & Personal AI Assistant» в текущей сессии. Ни дата исходных архитектурных сессий, ни их номера/оригинальные цитаты не предоставлены. Дата коммита импорта не является датой исторического утверждения.

Ниже сохранены формулировки A/B/C из предоставленной сейчас сводки на языке сообщения. Это текст текущей сводки владельца, а не цитаты из прежних сессий. Номера A.1–A.13, B.1–B.13 и C.1–C.5 адресуют только эту сводку. Вводимые H-A01–H-B13 — стабильные ID восстановления, не вымышленные исходные исторические ID.

Классификация A и B: OWNER_APPROVED_SUMMARY. Пакет C — отдельное owner-reported operational status, не архитектурное утверждение и не доказательство развёртывания.

Условия задания владельца: documentation only; сначала прочитать AGENTS.md и всю документацию 0A/0B; база сравнения — PR #2 и его ветка; отдельная ветка от 0B; не менять main и не объединять PR #2. Не создавать код, зависимости, контейнеры, инфраструктурные изменения, deployment, credentials, paid services или реальные интеграции. Все 26 пунктов учесть индивидуально, сохранить R01–R51/D01–D30, не считать агрегированные требования историческими решениями, явно отметить неопределённости и конфликты. Завершить documentation-only PR и остановиться; 0C-2 требует следующего задания владельца.

Правило приоритета из задания: предположение Codex не переопределяет owner-approved historical decision. Реальный конфликт двух подтверждённых решений регистрируется для владельца; решение за него не выбирается. Полный исторический реестр этим пакетом не восстанавливается.

## Package A — foundational architecture

<a id="a-1"></a>

1. AI Command Center is an owner-controlled AI director and orchestration system for multiple projects.

<a id="a-2"></a>

2. Primary interfaces: Telegram and a mobile-first web interface sharing the same authoritative task and approval state.

<a id="a-3"></a>

3. The control plane must remain operational independently of the home PC.

<a id="a-4"></a>

4. A permanently available VPS hosts the control plane; external cloud coding agents are launched on demand.

<a id="a-5"></a>

5. The system must support autonomous execution only within explicit permissions, limits, and approved requirements.

<a id="a-6"></a>

6. Owner approval is required for production deployment, irreversible actions, material architectural changes, new spending commitments, and external customer-facing actions.

<a id="a-7"></a>

7. An independent deterministic policy layer enforces permissions. AI judgment cannot bypass it.

<a id="a-8"></a>

8. All actions must have attributable evidence, durable records, and traceable outcomes.

<a id="a-9"></a>

9. Project requirements, approved decisions, Git revisions, tests, approvals, and results must remain linked.

<a id="a-10"></a>

10. Critical monitoring, emergency controls, audit history, and backups must not depend on the availability of AI providers.

<a id="a-11"></a>

11. The owner must be able to stop unsafe execution without granting agents unrestricted infrastructure credentials.

<a id="a-12"></a>

12. The system must not claim completion solely because an AI agent reports success.

<a id="a-13"></a>

13. Changes to previously approved requirements must follow a controlled review and versioning process.

## Package B — personal AI assistant and owner interaction

<a id="b-1"></a>

1. Safe and reversible tasks may be performed autonomously within defined boundaries; high-risk actions require approval.

<a id="b-2"></a>

2. The assistant supports planning, scheduling, priorities, reminders, and proactive identification of issues.

<a id="b-3"></a>

3. Notifications are prioritized and batched where appropriate; ordinary quiet hours are 23:00–08:00 local time, with exceptions for genuinely critical incidents.

<a id="b-4"></a>

4. Daily reports are planned for 08:00, 14:00, and 21:00 local time, with configurable delivery behavior.

<a id="b-5"></a>

5. Natural-language owner requests are translated into structured tasks with clear scope and acceptance criteria.

<a id="b-6"></a>

6. Persistent project knowledge is structured, versioned, and linked to its source and approval status.

<a id="b-7"></a>

7. The assistant may propose follow-up actions, but a suggestion or unanswered question is not owner consent.

<a id="b-8"></a>

8. Telegram voice messages can be transcribed and processed as owner instructions, subject to authentication and the same approval rules.

<a id="b-9"></a>

9. The assistant supports safe processing of screenshots, PDFs, spreadsheets, and attached files.

<a id="b-10"></a>

10. Telegram and mobile web must show consistent task status, approvals, incidents, and execution history.

<a id="b-11"></a>

11. New ideas can be captured and classified without unilaterally displacing approved priorities.

<a id="b-12"></a>

12. Planning adapts to verified project progress, dependencies, owner priorities, and available resources.

<a id="b-13"></a>

13. The owner receives concise, actionable summaries, with links to supporting evidence and detailed records.

## Package C — confirmed infrastructure status update

<a id="c-1"></a>

1. A VPS has already been purchased.

<a id="c-2"></a>

2. Console access is temporarily impaired during provider technical maintenance.

<a id="c-3"></a>

3. The server has not been authorized for configuration or deployment during Stage 0C.

<a id="c-4"></a>

4. Do not infer the VPS provider, region, credentials, exact plan, operating system, or readiness from this status update alone.

<a id="c-5"></a>

5. Preserve the previously approved infrastructure and budget principles, but do not misclassify the VPS purchase as pending.

Доступная база сравнения: [PR #2](https://github.com/v71369322-lang/ai-command-center/pull/2), ветка `docs/stage-0b-requirements`, коммит `edad9c6e9914e21025fe67a0417b7c45f036db28`. Оригинальные предыдущие сессии, полный реестр 128 пунктов и итоговый аудит не переданы; SRC-0C1 не подменяет их.
