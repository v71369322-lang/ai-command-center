# Влияние Stage 0C-2 на архитектуру и границы

Источник ограничений — [SRC-0C2](SOURCE_PACKAGE.md) и [26 записей](HISTORICAL_DECISION_REGISTER.md) OWNER_APPROVED_SUMMARY. Все варианты группировки, связи, последствия и будущие проверки в этом документе — **DERIVED**. Технические реализации не выбраны; тесты ниже не выполнялись.

## Управление проектами

| Область | Источник / прежние связи | Изменение полноты архитектуры | Предлагаемая будущая проверка / OPEN |
| --- | --- | --- | --- |
| Параллельность и первичный приоритет | H-C01,H-C08; R04,R38,R47; H-B11,H-B12 | Одновременно возможны несколько проектов, но один primary priority явно определён; verified incident policy ограничивает исключения | Проверить ограничение parallelism и запрет обычной AI-смены owner priority; U2-02 |
| AI PM и living knowledge | H-C02,H-C03; R05,R07,R11; H-B02,H-B06 | Roadmaps, decomposition, milestones, risks, acceptance; знания связываются с approved requirements/decisions/sources и implementation evidence | Устаревшее доказательство не выдаётся за актуальное; U2-04 |
| Readiness и dependency graph | H-C04,H-C07; R05,R06,R08; H-A12 | Зависимость незавершена/invalidated/unverified → dependent work блокируется; confidence агента не открывает запуск | Негативные сценарии неготового predecessor и истёкшего approval; U2-03/U2-05 |
| Requirement changes | H-C13; R07,R13; H-A13 | Impact analysis, versioning, dependency updates и owner approval material changes | Изменённый scope/architecture не исполняется со старой версией согласования; U2-03/U2-04 |

Это ответственность в рамках утверждённого modular monolith D03, не решение создать новый микросервис, graph DB, knowledge store или планировщик. CRM автосервиса остаётся PAUSED; Capital Lab и CRM кондитерской — самостоятельные внешние системы.

## Исполнение агентов

| Область | Источник / прежние связи | Ограничение будущей реализации | Предлагаемая проверка / OPEN |
| --- | --- | --- | --- |
| Hybrid execution и выбор провайдера | H-D01,H-D02,H-C11; R01,R16,R24,R35–R38; H-A04 | Persistent VPS + on-demand external agents; quality/capability/safety/cost/availability в разрешённом scope; resume/stop/events/artifacts не универсальны | Unsupported capability не объявляется исполненной, paid fallback не создаётся самовольно; U2-06 |
| Self-repair и разногласия | H-C05,H-D06,H-D07; R27,R38; H-A05,H-A07 | Bounded safe reversible corrections; bounded verification/escalation; запрет ослаблять критерии/тесты/лимиты/approvals | Исчерпание подтверждённого лимита останавливает цикл и передаёт вопрос; U2-08 |
| Recovery и checkpoints | H-C06,H-D08; R11,R21,R22; H-A08,H-A09 | Checkpoints/history/artifacts/status долговечны; после provider failure/crash сверяются actual agent/Git/external states | Прерывание после внешнего эффекта не ведёт к слепому retry/resume; U2-09 |
| Structured handoff | H-D13; R05,R07,R11,R13,R25; H-B06,H-B13 | Package содержит approved task, versions, dependencies, permissions, tests, evidence, unresolved questions и next safe actions | Отсутствующий scope или устаревшая версия не создаёт полномочий следующему агенту; U2-12 |

Handoff/PM/review описывают исторические требования к системе. В Stage 0C-2 исполнители и субагенты не запускаются, resume/stop API не вызываются, библиотеки очереди/AI SDK не выбираются.

## Границы безопасности и приёмка

| Область | Источник / прежние связи | Обязательная граница | Предлагаемая проверка / OPEN |
| --- | --- | --- | --- |
| Risk approvals и cards | H-C09,H-C10; R12,R13; H-A06,H-A07,H-B07 | Safe granted actions vs exact owner consent high risk; cards включают action/scope/risk/expected effects/relevant versions/expiry; детерминированный допуск проверяется независимо от AI/UI | Подмена параметров/версии, expiry и unanswered card не разрешают действие; U2-05 |
| Isolation и secrets | H-D03,H-D10; R15,R17,R18,R20,R23; H-A11 | Dedicated Git branches/worktrees, scoped file/API/network/credentials; нет unrestricted VPS admin, prod DB, cross-project credentials, unrelated data | Запрет доступа вне scope; дополнительных worktrees сейчас нет; U2-07 |
| Tiered verification и acceptance | H-C12,H-D04,H-D05; R06,R25,R26,R48; H-A12 | Static/unit/integration/contract/E2E/security according to risk; independent AI review significant дополнительно к deterministic tests; owner key milestones/MVP/production | Review success без checks не означает completion; AI не понижает risk для обхода owner acceptance; U2-08 |
| Supply chain и staged releases | H-D09,H-D11; R23,R33,R34,R51; H-A09 | Trusted CI, dependency review, pinned revisions, artifact integrity, staged checks, exact-release owner consent, post-release health | Артефакт без цепочки evidence не готов к выпуску; unsafe rollback и irreversible migration auto-rollback не разрешены; U2-10 |
| External API tests | H-D12; R19–R22,R45–R47 | Mocks/sandboxes где возможно; real calls лишь явно разрешённые; rate limits/idempotency/ambiguous outcome handling | Симулированный timeout после эффекта требует reconciliation; никаких real business calls сейчас; U2-11 |

Следствия не вводят подписи/аттестации определённого формата, worktree-management tool, CI vendor, isolation technology, выбранного AI reviewer или новое правило числа попыток. Это всё OPEN, а не APPROVED implementation.

## MVP scope

Состав MVP из [MVP_SCOPE](../../roadmap/MVP_SCOPE.md) и R49 сохранён: один изолированный тестовый исполнитель; нет полноценной бизнес-аналитики, торговли, автономных реальных CRM и сложного multi-agent planning. Нельзя объявить весь AI PM, multi-provider selection и reviewer disagreement orchestration обязательной новой функциональностью MVP только по факту импорта истории. Их scope allocation — U2-13, решение владельца.

Ограничения качества/безопасности применяются к любой разрешённой реализации в релевантном scope: evidence readiness, exact approvals, no weakened self-repair tests, independent AI review significant, owner MVP acceptance, provenance и reconciliation. Условия не становятся необязательными из-за неопределённого размещения функций в roadmap. A01 не заменяет acceptance H-C12.

Реальные проекты не подключаются для демонстрации multi-project readiness; автосервис не возобновляется. Текущий этап не разрешает даже MVP-каркас.

## Зависимости и порядок проверки

Связь с предложенными пакетами G1–G7 из 0B имеет класс DERIVED, не новый утверждённый календарный план:

| Прежний пакет | Дополнительные ограничения H | Что должно быть специфицировано до зависимой работы |
| --- | --- | --- |
| G1 структура/контракты | H-C03,H-C07,H-C13,H-D03,H-D10,H-D11 | Версии/ownership/dependency validity, file/API/network/credential boundaries, source pinning; D18,D19,D21,D25 |
| G2 state/dopusk/budget | H-C01,H-C02,H-C04,H-C08,H-C09,H-C10,H-C11 | Primary priority/incident permissions, readiness/approval cards, выбор модели без обхода резерва/лимитов; D20,D22–D24 |
| G3 исполнение/recovery | H-C05,H-C06,H-D01,H-D02,H-D06,H-D07,H-D08,H-D13 | Provider capabilities, bounded recovery/repair/escalation, durable checkpoints и structured handoff; D20–D25 |
| G4 каналы | H-C10; H-B10 | Одинаковая action version/approval status/expiry, аутентификация; D23 |
| G5 приёмка | H-C12,H-D04,H-D05 | Risk-to-check matrix и owner acceptance MVP; D29 |
| G6 эксплуатация | H-D09,H-D11 | Exact release identity, CI/build evidence, health gates и безопасный rollback; D26,D27 |
| G7 внешние интеграции | H-D12; R46,R47 | Отдельное разрешение каждого проекта и real-call tests; D28 |

Старая G-матрица не является полным task-level dependency graph H-C07. Граф зависимостей проекта/задач, capability matrix провайдеров и roadmap поставки — разные модели; их контракты ещё OPEN. Новая потребность не считается реализованной из-за добавленной таблицы.

[Статус инфраструктуры](../../architecture/INFRASTRUCTURE_STATUS.md) сохранён без технического обновления: VPS уже куплен по сообщению владельца, console access reported impaired; не проверялся и не настраивался. R35–R40/H-A06 остаются: budget ceiling не разрешение покупки, unknown costs не вычитаются по предположению. Текущая работа — только документация.
