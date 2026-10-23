# Открытые технические предположения и вопросы

Статус: не утверждено. Ниже перечислены вопросы для проверки в последующих заданиях, а не выбранные решения. Из задания этапа 0A нельзя вывести ответы или считать, что исторический контекст уже полностью известен.

| Область | Что требует проверки и согласования |
| --- | --- |
| Среда исполнения | Совместимые версии Python, Node.js, PostgreSQL и Redis, версии зависимостей и базовые образы. Конкретные версии пока не утверждены. |
| Модули | Состав модулей монолита, границы ответственности, внутренние контракты и владение данными. |
| Очереди | Библиотека для Python workers, гарантии доставки, идемпотентность, отмена, восстановление и проверка результата внешних операций после таймаута. Redis уже утверждён, библиотека очередей — нет. |
| Изоляция агентов | Механизм облачной изоляции, выдача минимальных прав, ограничение сети, срок жизни среды и очистка ресурсов. |
| Адаптеры AI | Контракт провайдеров, поддерживаемые возможности, учёт стоимости и ограничения каждого провайдера. Реальные подключения на этапе 0A запрещены. |
| Идентификация и согласования | Аутентификация владельца, связь Telegram и веб-панели, модель версии действия, срок действия подтверждений, защита от повторного исполнения и журналирование. |
| Расходы | Источники тарифов и курсов, состав новых расходов, расчёт резервов, конкурентные запуски и поведение при достижении лимитов в рамках утверждённого ориентира. |
| Данные и секреты | Классификация данных, сроки хранения, редактирование персональных данных, хранение и выдача секретов, разграничение доступа проектов. |
| VPS и восстановление | Требования к ресурсам, независимые мониторинг и аварийный доступ, размещение резервных копий и проверка восстановления. Выбор и настройка VPS сейчас не разрешены. |
| Релизы и БД | Проверки перед релизом, миграции, критерии совместимости состояния БД и доказательства безопасности автоматического отката. |
| Будущие интеграции | Допустимые операции и минимальные права для каждого внешнего проекта; подключение требует отдельного разрешения. |
| Приёмка MVP | Проверяемые сценарии, объём базового мониторинга и критерии готовности первого изолированного тестового агента. |

## Недостающие материалы

Полный реестр архитектурных решений и итоговый аудит будут переданы отдельными заданиями. После получения потребуется сопоставить их с исходными принципами и уточнить открытые вопросы, не подменяя решения владельца предположениями.

Объём этапа 0B пока не задан. Ожидается отдельное задание; автоматически продолжать реализацию нельзя.

## Дополнение этапа 0B

Задание владельца на 0B получено отдельно; оно разрешает документальные реестры и PR, но не реализацию приложения. Фраза выше о невыданном 0B сохранена как исходный контекст этапа 0A.

Исходные 12 областей вопросов сопоставлены с OPEN D18–D29 в [реестре решений](decisions/DECISION_REGISTER.md). Ни один технический вариант за владельца не выбран.

| ID | Статус | Допущение | Проверка и последствие неподтверждения |
| --- | --- | --- | --- |
| A01 | ASSUMPTION | Для первого сквозного теста достаточно синтетической задачи без клиентских данных | Владелец уточняет сценарий и доказательства в D29 до S5; при неподтверждении пересматриваются сценарий R48 и приёмка, реальные данные автоматически не разрешаются |

Неполнота исторических источников и условия передачи в 0C перечислены в [TRACEABILITY_GAPS](TRACEABILITY_GAPS.md). Это дополнение не закрывает исходные вопросы и не утверждает предложенную последовательность реализации.

## Дополнение Stage 0C-1

26 решений [исторической сводки](history/stage-0c-1/HISTORICAL_DECISION_REGISTER.md) имеют класс OWNER_APPROVED_SUMMARY, а не ASSUMPTION. Сопоставления имеют класс DERIVED; конкретные неопределённости вынесены в [U01–U12](history/stage-0c-1/CONFLICTS_AND_UNCERTAINTIES.md). Новых предположений не добавлено. A01 остаётся непроверенным и не вправе ослаблять H-A12 или другое решение владельца.

Уточнение области «VPS и восстановление»: [Package C](architecture/INFRASTRUCTURE_STATUS.md) сообщает, что VPS уже куплен. Покупка не является pending/предположением; неизвестны технические детали, доступность и readiness. Формулировка 0A о выборе/настройке сохраняет исторический контекст и не отменяет этот новый сообщённый факт. Конфигурация и deployment Stage 0C не разрешены.

Точные тихие часы 23:00–08:00 local и ежедневные отчёты 08:00/14:00/21:00 local утверждены сводкой (H-B03/H-B04); неизвестны timezone владельца и правила configurable delivery. UTC окружения не выбирается вместо local time. D18–D29 не закрываются фактом получения сводки; задан только документальный подэтап 0C-1.

## Дополнение Stage 0C-2

Новые [26 исторических записей H-C/H-D](history/stage-0c-2/HISTORICAL_DECISION_REGISTER.md) имеют OWNER_APPROVED_SUMMARY из [SRC-0C2](history/stage-0c-2/SOURCE_PACKAGE.md), не ASSUMPTION. Новых допущений — 0. A01 остаётся непроверенным и не может ослабить tiered acceptance H-C12, layered checks H-D04 или independent AI review H-D05.

[U2-01–U2-13](history/stage-0c-2/CONFLICTS_AND_UNCERTAINTIES.md) отделяют утверждённые нормы от OPEN реализации: логический dependency graph/readiness, primary priority/approved incident policy, approval cards, provider capabilities, bounded repair/escalation, checkpoints, scoped worktrees/environments, trusted CI/provenance, controlled external tests и handoff. Не выбраны graph DB, queue library, CI/signature mechanism, AI reviewer/model, численные caps или форматы хранения/протоколов.

D18–D29 сохраняют статус OPEN в части технических механизмов; новые обязанности не закрывают их автоматически. VPS остаётся уже купленным по сообщению владельца; технической проверки нет. Старые U 0C-1 не переписаны; предоставлена тема только 0C-2, дальнейшее задание 0C-3 отсутствует.

## Дополнение Stage 0C-3

[29 записей H-E/H-F](history/stage-0c-3/HISTORICAL_DECISION_REGISTER.md) — OWNER_APPROVED_SUMMARY из [SRC-0C3](history/stage-0c-3/SOURCE_PACKAGE.md), не ASSUMPTION. Relation categories/impact — DERIVED. Новых допущений нет; A01 остаётся непроверенным и не становится подтверждённым из-за synthetic default H-F10.

[U3-01–U3-16](history/stage-0c-3/CONFLICTS_AND_UNCERTAINTIES.md) сохраняют OPEN: metric/incident state criteria, polling/dedup, remediation policy/real-change scope, exact budget accounting, localization/legal basis, offsite/recovery/test evidence, actual credential enforcement, provider fallback/stop guarantees, concurrency/lease mechanisms и parameters, exact provenance. Hard ceiling/70-90-100 controls и source-approved named mechanisms не оставлены вопросами; их concrete implementation/численные caps не выбраны.

Численные RPO ≤15 минут/RTO ≤4 часов в baseline не найдены, только OPEN RPO/RTO. Conditional safeguard текущего source не задаёт новый target; такие previously discussed values при появлении источника — provisional feasibility targets, не tested operational performance. Не изобретены retry limits, TTL, retention или гарантии.

D18–D29 не закрыты автоматически общим принципом. Не выбраны новый microservice или permanent second VPS по умолчанию. VPS purchase остаётся reported completed; console availability/configuration/readiness не проверены. Scope Stage 0C-3 — документация; тема 0C-4 и programming не разрешены.

## Дополнение Stage 0C-4

[26 H-G/H-H](history/stage-0c-4/HISTORICAL_DECISION_REGISTER.md) имеют OWNER_APPROVED_SUMMARY из [SRC-0C4](history/stage-0c-4/SOURCE_PACKAGE.md), не Codex assumption. Новых ASSUMPTION нет. Reconciliation/implementation interpretations DERIVED; concrete details — [OPEN U4-01–U4-16](history/stage-0c-4/CONFLICTS_AND_UNCERTAINTIES.md).

Явные source-backed уточнения: H-H02 approximate 2–4 vCPU/4–8 GB/SSD planning target; H-H03 initial Ubuntu LTS/pinned Compose/security approach; H-H06 provisional RPO≤15min/RTO≤4h и WAL/PITR where feasible. Это не original deployed specs, выбранные concrete versions или proven guarantees. Current purchased configuration/provider/region/OS/security/billing/readiness неизвестны; FirstVDS Almaty/prices planning context не проверен как current fact.

Старый D26/U3-07 теперь частично уточнён target values, но не feasibility/resources/measurement/drills. D18/D25 вопросы конкретных versions/secret mechanism также не закрываются initial family/broker-or-equivalent требованием. Никакого выбранного vendor/new microservice/второго VPS или read actual customer data.

H-H11 прямо утверждает isolated synthetic E2E starting pattern; A01 sufficiency конкретного теста/готовности MVP этим не доказана, historical ASSUMPTION не переписан. KPI formulas/accounting/attribution/forecast methods, customer identities и Ytimes/storefront matching rules не изобретены. Исторические U/U2/U3 сохранены; дальнейшая тема 0C-5 не предоставлена.
