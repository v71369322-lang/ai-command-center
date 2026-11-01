# Конфликты и неопределённости Stage 0C-2

Источник [SRC-0C2](SOURCE_PACKAGE.md), база `301b07de174ad0da049813a24ede64dc3f4a04d0`. Класс решений — OWNER_APPROVED_SUMMARY. Сверка ниже — DERIVED.

## Подтверждённые CONFLICT

**0 подтверждённых конфликтов** между доступными owner-approved решениями. Это ограниченный результат сверки 0A/0B/0C-1 и текущей сводки, не вывод о всей недоступной истории.

| Потенциальное противоречие | Разбор области действия (DERIVED) | Что сохраняется / что OPEN |
| --- | --- | --- |
| H-D03 branches/worktrees и AGENTS.md: не создавать additional worktrees без явного запроса | Исторический принцип изоляции не является запросом создавать worktree в документационной задаче | AGENTS.md не изменён, worktrees не создаются. Будущее сочетание branch/worktree и отдельная авторизация — U2-07 |
| H-C08 incident priorities и H-B11/H-B12 owner priorities | Исключение относится только к verified critical incident и уже approved incident policy; не к предпочтению AI | Вне policy приоритеты не меняются; incident не отменяет H-A06/H-A07. Сама policy — U2-02/U2-05 |
| H-C12 low-risk automated acceptance и H-D04/H-D05 independent AI review | Разные уровни риска: significant changes требуют независимого AI review дополнительно к deterministic checks; key milestones/MVP/production — owner acceptance | «Low-risk» нельзя самовольно использовать для снижения класса и обхода обязательных тестов/approvals; risk matrix — U2-08 |
| H-C05/H-D07 self-repair и controlled changes H-A13/H-C13 | Self-repair не ослабляет approved requirements, tests, budgets, permissions. Разрешённое owner change проходит отдельный контроль версий/impact | Нельзя удалять failing tests ради успеха или подменять acceptance. Параметры limits — U2-08 |
| H-D09 production release и запрет deployment Stage 0C | Норма будущего выпуска не разрешает выполнить его сейчас | Exact release approval и health обязательны в будущем; текущий запрет deployments, VPS checks и real integrations остаётся |
| H-C11 выбор availability/cost и H-A06/R35–R40 | Критерии выбора модели ограничены confirmed provider permissions и spending limits | Budget ceiling не разрешает новые commitments или произвольный paid fallback |
| H-C02/H-D06/H-D13 и R49: no complex multi-agent planning in MVP | Future AI PM/reviewer/handoff responsibilities не объявляют сложное мультиагентное планирование частью MVP | Никакой новый autonomous agent в этом задании не запускается; allocation — U2-13 |

Правило эскалации подтверждённого конфликта: зафиксировать обе несовместимые нормы с точными источниками H/R/D, scope и последствиями; передать владельцу; не выбрать победителя и не продолжать зависимое опасное действие. Наличие OPEN детали не является CONFLICT и не отменяет норму. В этом пакете такого выбора не потребовалось.

## OPEN: детали и недостающие evidence

13 групп U2-01–U2-13. Это не 13 дополнительных исторических решений и не отмена OWNER_APPROVED_SUMMARY. Старые U01–U12 0C-1 не перенумерованы; cross-links указаны явно.

| ID | Связанные записи | Чего нет | Ограничение / что нужно уточнить |
| --- | --- | --- | --- |
| U2-01 | Все 26 H-C/H-D; GAP01–GAP04; 0C-1 U01 | Нет оригинальных сессий, исторических timestamps/IDs, альтернатив, полной истории approvals/замен, полного реестра 128 пунктов и аудита. | Сохранить current summary и supplied IDs; не выдумывать исторические источники и не считать импорт доказательством реализации. |
| U2-02 | H-C01,H-C08; H-B03,H-B11,H-B12; R04,R47 | Не назван текущий primary priority, нет численного parallelism cap и approved incident policy: critical verification, допустимые смены приоритета, полномочия и возврат. | Владелец задаёт policy/приоритеты; PAUSED CRM не возобновляется. Verified incident не даёт новых прав, бюджета или согласия на опасное действие. |
| U2-03 | H-C02,H-C04,H-C07,H-C13; D19,D20 | Не выбраны схема dependency graph, правила prerequisite validity/invalidation, cycles, readiness и изменения downstream tasks. | Утверждён граф как логическая модель и блокировка incomplete/invalidated/unverified predecessors; graph DB/алгоритм/библиотека не выбираются. |
| U2-04 | H-C02,H-C03,H-C13; H-B06; D19,D25; 0C-1 U06 | Не определены роль/контракты AI PM, структура knowledge, freshness evidence, impact analysis, версия scope/decisions и хранение. | Уточнить связь approved requirements/decisions/source/evidence; автоматический план не изменяет approved scope без требуемого owner approval. |
| U2-05 | H-C04,H-C08,H-C09,H-C10; H-A06,H-A07,H-B07; D23; 0C-1 U02 | Не определены risk categories, critical policy, UX cards, точное кодирование action/scope/effects/versions/expiry, аутентификация, TTL и отзыв. | Поля cards и exact consent утверждены; конкретный формат и интерфейс OPEN. Policy остаётся детерминированной, молчание не согласие. |
| U2-06 | H-C11,H-D01,H-D02; D22,D24; 0C-1 U07 | Нет approved provider/model matrix, формата capabilities, quality/cost thresholds, fallback и поведения unsupported stop/resume/events/artifacts. | Не объявлять capability универсальной, выбирать провайдера только в подтверждённых правах/лимитах. Не подключать или покупать сервисы этим заданием. |
| U2-07 | H-C05,H-D03,H-D10; D21,D25; AGENTS.md | Не выбраны scoped environment, Git branch/worktree arrangement, file/API/network/credential grants, выдача/отзыв/очистка secrets. | Историческая изоляция не запрашивает worktree в этом задании. Scope/least privilege не снимаются; реальные данные и credentials не используются. |
| U2-08 | H-C05,H-C12,H-D04,H-D05,H-D06,H-D07; D29; 0C-1 U11 | Не определены risk-to-test matrix, significant/key milestone thresholds, критерии независимости AI review, limits disagreement/self-repair и escalation evidence. | Не выбирать модель reviewer или число попыток; deterministic tests, owner milestone/MVP acceptance и approvals остаются обязательны. A01 не доказывает приёмку. |
| U2-09 | H-C06,H-D02,H-D08; D20,D22 | Нет checkpoint/artifact/status contracts, recovery protocol, правил сверки agent/Git/external states и неизвестных исходов. | Resume/retry только после сверки; наличие checkpoint не доказывает внешний результат или безопасное продолжение. |
| U2-10 | H-D09,H-D11; R34,R51; D18,D27; 0C-1 U07 | Не выбраны staged release gates, trusted CI evidence, dependency review, pinned revision/artifact format, exact release identity, health criteria и compatibility rollback. | Утверждены обязанности, не CI product/signing mechanism. Нельзя пропускать consent или автоматически откатывать необратимую миграцию. |
| U2-11 | H-D12; R21,R45,R46,R47; D28 | Не определены API-specific mocks/sandboxes, rate limits, idempotency keys, real-call permissions, reconciliation и обработка данных. | Mocks/sandboxes where possible, реальные вызовы только по отдельному явному разрешению. Capital Lab/CRM самостоятельны; trading/customer operations не разрешены. |
| U2-12 | H-D13; H-A05,H-A08,H-A09,H-B06; D19,D22 | Не определены handoff schema, integrity, evidence access, freshness, receiving acknowledgement и next-safe-action validation. | Утверждён состав context package, не транспорт/формат. Передача данных не повышает permissions и не превращает недоверенный текст в команду. |
| U2-13 | H-C02,H-C11,H-C12,H-D01,H-D06,H-D13; D16,D29; 0C-1 U09,U10 | Не утверждены allocation новых возможностей в MVP/после MVP, детальные acceptance criteria, тема и состав 0C-3. | Сохранить one test executor и исключение сложного multi-agent planning; отдельное задание владельца на 0C-3. Ни код, ни VPS-доступ не разрешены. |

## ASSUMPTION и provenance

Новых ASSUMPTION — **0**. Старое A01 о достаточности синтетического теста остаётся непроверенным и не может переопределить H-A12,H-C12,H-D04,H-D05,H-D07. Выводы о будущих checks в [impact report](IMPACT_REPORT.md) имеют класс DERIVED и не являются результатами выполненных тестов.

0C-1 U10: тема 0C-2 теперь предоставлена SRC-0C2; исходный отчёт сохранён как историческое состояние. Это не закрывает тему/задание 0C-3 (U2-13), остальные вопросы старого отчёта или GAP01–GAP07. OPS-C01–OPS-C05 остаются owner-reported operational status: VPS purchased, console impairment reported; новых технических сведений нет.
