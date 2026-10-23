# Границы MVP

APPROVED: состав из U3 и ограничения 0A. [Полные формулировки R](../requirements/REQUIREMENTS_REGISTER.md). Сопоставление — DERIVED. MVP пока не реализован; документ не разрешает запуск или расходы.

| Пункт U3 | Обязательный состав | Требования | Проверка / этап |
| --- | --- | --- | --- |
| 1 | Telegram-бот | R02,R44 | Ввод и отчёт / S4 |
| 2 | Mobile-first веб-панель | R03,R44 | Мобильный экран и общее состояние / S4 |
| 3 | API и оркестратор | R05,R10,R12 | Жизненный цикл и допуск / S2 |
| 4 | PostgreSQL | R09,R11 | Сохранение и восстановление / S2,S6 |
| 5 | Redis и очередь | R09,R29 | Передача и восстановление / S2,S3 |
| 6 | Один изолированный тестовый исполнитель | R16,R17,R24 | Ограниченные права / S3 |
| 7 | Журнал задач и результатов | R06,R11 | Фактическое доказательство / S2,S5 |
| 8 | Подтверждения владельца | R12,R13,R14 | Неверная версия, срок, отзыв / S2,S3 |
| 9 | Базовые расходы и лимиты | R35–R40 | Резервы, гонки, пороги / S2–S4 |
| 10 | Базовый мониторинг и аварийная остановка | R28,R30,R41 | Отказ и запрет дальнейших действий / S3,S4,S6 |
| 11 | Telegram → оркестратор → агент → результат → Telegram/web | R48 | Сквозной протокол / S5 |

Обязательные сквозные ограничения MVP: R04,R07,R08,R15,R18–R23,R25–R27,R31–R34,R45,R49,R51. Они не превращаются в необязательные из-за слова «базовый». Несколько проектов проверяются на синтетических пространствах; это не подключение реальных CRM. Один исполнитель не означает сложное мультиагентное планирование. Полноценная поддержка нескольких реальных провайдеров не требуется для первого сквозного теста, но контракт адаптера обязателен; конкретный тестовый режим OPEN D22,D29.

За пределами MVP (APPROVED): полноценная бизнес-аналитика (R42,R43), торговые операции, автономное управление реальными CRM, сложное мультиагентное планирование (R49). Отдельные будущие подключения (R46,R47) не разрешены ни этим реестром, ни успешной приёмкой MVP. Маркетинговые расходы, клиентские сообщения и финансовые операции не делегируются автоматически (R45).

Предлагаемые условия готовности (DERIVED): все применимые P0 имеют проверяемые доказательства и независимое ревью; OPEN, мешающие безопасности, закрыты владельцем; сквозной тест и негативные сценарии успешны; перед эксплуатацией выполнен S6. Неопределённые значения таймаутов, RPO/RTO, SLA и лимитов не заменяются придуманными числами.

## Сверка с историей Stage 0C-1

Источник [SRC-0C1](../history/stage-0c-1/SOURCE_PACKAGE.md), [пункты H](../history/stage-0c-1/HISTORICAL_DECISION_REGISTER.md), [матрица](../history/stage-0c-1/RECONCILIATION_MATRIX.md). Утверждённые ограничения foundation действуют и при последующей реализации MVP; производные проверки и допущение A01 их не переопределяют.

Восстановленные функции assistant (scheduling/reminders/proactivity, quiet hours 23:00–08:00 local, отчёты 08:00/14:00/21:00 local, versioned project knowledge, voice, safe attachments, ideas capture) не имели полной спецификации в baseline 0B. Их исторический статус OWNER_APPROVED_SUMMARY сохранён. Размещение в MVP/после MVP — OPEN U09; это задание не включает их автоматически в MVP и не отменяет их. Нельзя считать quiet hours или время отчётов неутверждёнными только потому, что timezone и delivery details ещё OPEN U03.

Обязательны одинаковое состояние incidents/history в двух интерфейсах (H-B10), план по verified progress и ресурсам без вытеснения приоритетов идеями (H-B11/H-B12), краткие actionable reports со ссылками на evidence (H-B13). Критерии реализации уточняются отдельным заданием. Stage 0C-1 не разрешает приложение, paid services или infrastructure.

## Сверка Stage 0C-2: принятие результата и границы автономности

[Источник SRC-0C2](../history/stage-0c-2/SOURCE_PACKAGE.md), [26 записей H-C/H-D](../history/stage-0c-2/HISTORICAL_DECISION_REGISTER.md), [impact](../history/stage-0c-2/IMPACT_REPORT.md). Прежняя таблица состава MVP и R49 сохранены. Новые исторические возможности project manager/model selection/reviewer orchestration/handoff не добавляются автоматически в MVP и не отменяются; scope allocation — OPEN U2-13, решение владельца.

Нормативные ограничения H-C04/H-C05/H-C09/H-C12/H-D04/H-D05/H-D07 применяются к релевантной разрешённой реализации: readiness по prerequisites/evidence, no weakened repair criteria/tests, exact approvals, tiered checks, independent AI review significant и owner acceptance ключевых milestones/MVP/production. Самоотчёт агента или A01 не заменяет такую приёмку.

Сохраняются один изолированный тестовый исполнитель, отсутствие complex multi-agent planning, trading, real autonomous CRM и полноценной аналитики. Project concurrency не означает подключение реальных проектов. Capital Lab/CRM кондитерской самостоятельны; автосервис PAUSED. Stage 0C-2 — только документация, без MVP implementation, VPS checks, real API calls или платных действий.

## Сверка Stage 0C-3: monitoring/recovery constraints

[Source](../history/stage-0c-3/SOURCE_PACKAGE.md), [29 H-E/H-F](../history/stage-0c-3/HISTORICAL_DECISION_REGISTER.md), [impact](../history/stage-0c-3/SECURITY_AND_RECOVERY_IMPACT.md). Прежний MVP состав и R49 сохранены: один test executor, без полноценной analytics/trading/автономных real CRM/complex multi-agent planning. Новые dashboard/incident/functional-health возможности не включаются в MVP автоматически и не отменяются; scope allocation OPEN U3-16.

Нормы actual deterministic permissions/default deny, data/environment isolation, hard spending ceiling, independent monitoring/emergency/AI-outage controls, bounded execution/leases/concurrency/reconciliation, versioned completion/release evidence и exact restore/dangerous approvals применяются к релевантной будущей разрешённой реализации. Неопределённый roadmap не делает их необязательными.

Business-functional health не смешивается с infrastructure outage; unknown/stale/paused не healthy. Planned backups/recovery/preflight не являются tested restoration или readiness. Synthetic default H-F10 не закрывает A01 и не заменяет H-C12/H-F09 owner/evidence acceptance.

VPS purchased/console impairment — owner-reported факты без readiness; preflight/access/customer data/implementation/paid actions Stage 0C-3 запрещены. Capital Lab/CRM кондитерской самостоятельны, CRM автосервиса PAUSED. Permanent second VPS не default MVP requirement; существенные новые расходы требуют разрешения независимо от ceiling.
