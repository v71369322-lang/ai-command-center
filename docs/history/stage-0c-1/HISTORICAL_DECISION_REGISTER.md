# Исторический реестр: Foundation & Personal AI Assistant

Версия восстановления: 0C-1.1. Источник всех 26 строк — [SRC-0C1](SOURCE_PACKAGE.md), Package A/B с адресом пункта. Это первый тематический пакет, не полный исторический реестр.

| Класс | Значение |
| --- | --- |
| OWNER_APPROVED_SUMMARY | Содержание утверждено владельцем в предоставленной исторической сводке; оригинальные сессии/даты не получены |
| DERIVED | Сопоставление, группировка, предложенные проверки и последствия, подготовленные при восстановлении |
| ASSUMPTION | Непроверенное допущение; в 0B имеется A01, оно не переопределяет решения владельца |
| OPEN | Ответ, конкретизация или доказательство отсутствуют |
| CONFLICT | Два подтверждённых решения несовместимы; разрешает только владелец |

Ни одно OWNER_APPROVED_SUMMARY не становится ASSUMPTION из-за отсутствия оригинального протокола. Никакое DERIVED не расширяет права. Утверждение принципа не является разрешением его реализовать на Stage 0C.

| Стабильный ID восстановления | Источник | Классификация | Содержание supplied summary |
| --- | --- | --- | --- |
| H-A01 | [SRC-0C1 A.1](SOURCE_PACKAGE.md#a-1) | OWNER_APPROVED_SUMMARY | AI Command Center is an owner-controlled AI director and orchestration system for multiple projects. |
| H-A02 | [SRC-0C1 A.2](SOURCE_PACKAGE.md#a-2) | OWNER_APPROVED_SUMMARY | Primary interfaces: Telegram and a mobile-first web interface sharing the same authoritative task and approval state. |
| H-A03 | [SRC-0C1 A.3](SOURCE_PACKAGE.md#a-3) | OWNER_APPROVED_SUMMARY | The control plane must remain operational independently of the home PC. |
| H-A04 | [SRC-0C1 A.4](SOURCE_PACKAGE.md#a-4) | OWNER_APPROVED_SUMMARY | A permanently available VPS hosts the control plane; external cloud coding agents are launched on demand. |
| H-A05 | [SRC-0C1 A.5](SOURCE_PACKAGE.md#a-5) | OWNER_APPROVED_SUMMARY | The system must support autonomous execution only within explicit permissions, limits, and approved requirements. |
| H-A06 | [SRC-0C1 A.6](SOURCE_PACKAGE.md#a-6) | OWNER_APPROVED_SUMMARY | Owner approval is required for production deployment, irreversible actions, material architectural changes, new spending commitments, and external customer-facing actions. |
| H-A07 | [SRC-0C1 A.7](SOURCE_PACKAGE.md#a-7) | OWNER_APPROVED_SUMMARY | An independent deterministic policy layer enforces permissions. AI judgment cannot bypass it. |
| H-A08 | [SRC-0C1 A.8](SOURCE_PACKAGE.md#a-8) | OWNER_APPROVED_SUMMARY | All actions must have attributable evidence, durable records, and traceable outcomes. |
| H-A09 | [SRC-0C1 A.9](SOURCE_PACKAGE.md#a-9) | OWNER_APPROVED_SUMMARY | Project requirements, approved decisions, Git revisions, tests, approvals, and results must remain linked. |
| H-A10 | [SRC-0C1 A.10](SOURCE_PACKAGE.md#a-10) | OWNER_APPROVED_SUMMARY | Critical monitoring, emergency controls, audit history, and backups must not depend on the availability of AI providers. |
| H-A11 | [SRC-0C1 A.11](SOURCE_PACKAGE.md#a-11) | OWNER_APPROVED_SUMMARY | The owner must be able to stop unsafe execution without granting agents unrestricted infrastructure credentials. |
| H-A12 | [SRC-0C1 A.12](SOURCE_PACKAGE.md#a-12) | OWNER_APPROVED_SUMMARY | The system must not claim completion solely because an AI agent reports success. |
| H-A13 | [SRC-0C1 A.13](SOURCE_PACKAGE.md#a-13) | OWNER_APPROVED_SUMMARY | Changes to previously approved requirements must follow a controlled review and versioning process. |
| H-B01 | [SRC-0C1 B.1](SOURCE_PACKAGE.md#b-1) | OWNER_APPROVED_SUMMARY | Safe and reversible tasks may be performed autonomously within defined boundaries; high-risk actions require approval. |
| H-B02 | [SRC-0C1 B.2](SOURCE_PACKAGE.md#b-2) | OWNER_APPROVED_SUMMARY | The assistant supports planning, scheduling, priorities, reminders, and proactive identification of issues. |
| H-B03 | [SRC-0C1 B.3](SOURCE_PACKAGE.md#b-3) | OWNER_APPROVED_SUMMARY | Notifications are prioritized and batched where appropriate; ordinary quiet hours are 23:00–08:00 local time, with exceptions for genuinely critical incidents. |
| H-B04 | [SRC-0C1 B.4](SOURCE_PACKAGE.md#b-4) | OWNER_APPROVED_SUMMARY | Daily reports are planned for 08:00, 14:00, and 21:00 local time, with configurable delivery behavior. |
| H-B05 | [SRC-0C1 B.5](SOURCE_PACKAGE.md#b-5) | OWNER_APPROVED_SUMMARY | Natural-language owner requests are translated into structured tasks with clear scope and acceptance criteria. |
| H-B06 | [SRC-0C1 B.6](SOURCE_PACKAGE.md#b-6) | OWNER_APPROVED_SUMMARY | Persistent project knowledge is structured, versioned, and linked to its source and approval status. |
| H-B07 | [SRC-0C1 B.7](SOURCE_PACKAGE.md#b-7) | OWNER_APPROVED_SUMMARY | The assistant may propose follow-up actions, but a suggestion or unanswered question is not owner consent. |
| H-B08 | [SRC-0C1 B.8](SOURCE_PACKAGE.md#b-8) | OWNER_APPROVED_SUMMARY | Telegram voice messages can be transcribed and processed as owner instructions, subject to authentication and the same approval rules. |
| H-B09 | [SRC-0C1 B.9](SOURCE_PACKAGE.md#b-9) | OWNER_APPROVED_SUMMARY | The assistant supports safe processing of screenshots, PDFs, spreadsheets, and attached files. |
| H-B10 | [SRC-0C1 B.10](SOURCE_PACKAGE.md#b-10) | OWNER_APPROVED_SUMMARY | Telegram and mobile web must show consistent task status, approvals, incidents, and execution history. |
| H-B11 | [SRC-0C1 B.11](SOURCE_PACKAGE.md#b-11) | OWNER_APPROVED_SUMMARY | New ideas can be captured and classified without unilaterally displacing approved priorities. |
| H-B12 | [SRC-0C1 B.12](SOURCE_PACKAGE.md#b-12) | OWNER_APPROVED_SUMMARY | Planning adapts to verified project progress, dependencies, owner priorities, and available resources. |
| H-B13 | [SRC-0C1 B.13](SOURCE_PACKAGE.md#b-13) | OWNER_APPROVED_SUMMARY | The owner receives concise, actionable summaries, with links to supporting evidence and detailed records. |

ID H не заменяют R/D. Подтверждения и уточнения привязаны к прежним записям в [матрице](RECONCILIATION_MATRIX.md), а полностью не покрытые 0B пункты явно выделены. Новые записи R/D в этом пакете не создаются, чтобы не дублировать историческое утверждение как якобы ещё одно решение.

Применимость: требования согласований, доказательств, детерминированной политики и неизменности приоритетов ограничивают любую будущую реализацию. Функции ассистента, отсутствующие в 0B, сохраняются как утверждённый исторический объём; их размещение в MVP/после MVP остаётся OPEN, а не автоматически POST или новое разрешение разработки.

Историческая дата принятия, оригинальный ID, участники сессии, альтернативы и цепочка замен для каждой строки: OPEN / не предоставлены. Фактическая реализация и приёмочные доказательства для каждой строки: не проверялись и не заявляются. См. [неопределённости](CONFLICTS_AND_UNCERTAINTIES.md) и [покрытие](COVERAGE_REPORT.md).
