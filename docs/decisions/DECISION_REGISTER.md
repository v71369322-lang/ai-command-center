# Реестр доступных архитектурных решений

Версия 0B.1. 30 записей: 18 APPROVED (агрегированные принципы), 12 OPEN (вопросы, не принятые решения). Это не восстановление полного исторического реестра. Статусы и источники определены в [реестре требований](../requirements/REQUIREMENTS_REGISTER.md). DERIVED описывает предлагаемые связи и порядок, ASSUMPTION — только явные допущения из [OPEN_ASSUMPTIONS](../OPEN_ASSUMPTIONS.md).

Для APPROVED основание — указанный источник владельца; дата первоначального исторического решения и альтернативы неизвестны. Общие последствия: реализация должна сохранять ограничение; конкретный механизм выбирается только после разрешения соответствующего OPEN. Этап и связи — DERIVED.

| ID | Статус | Решение / вопрос | Источник | Требования | Этап |
| --- | --- | --- | --- | --- | --- |
| D01 | APPROVED | Постоянный облачный контур, Telegram и mobile-first web с общим состоянием | U2/Управление; P; B7 | R01,R02,R03,R44 | S4,S6 |
| D02 | APPROVED | Независимые проекты, управляемый жизненный цикл и версионирование | U2/Управление проектами | R04,R05,R06,R07,R08 | S1,S2,S5 |
| D03 | APPROVED | Утверждённый стек, модульный монолит и Compose; очередь и Python workers | B1–6; U3.3–5 | R09,R10,R29 | S1,S2 |
| D04 | APPROVED | Журнал задач, результатов, согласований, запусков и действий | U2/Надёжность | R11 | S2 |
| D05 | APPROVED | Владелец разрешает опасные действия; независимая проверка, точная версия и срок; саморасширение прав запрещено | B11–12; U2/Безопасность | R12,R13,R14 | S2,S3 |
| D06 | APPROVED | Изоляция сред и проектов, защита секретов, данных и от prompt injection | B19; A; U2/Безопасность | R15,R18,R19,R20 | S1,S3 |
| D07 | APPROVED | Изолированные облачные исполнители по запросу, один тестовый в MVP, минимальные права | B10; U3.6; U2/Надёжность | R16,R17 | S3 |
| D08 | APPROVED | Неизвестный исход сверяется перед повтором; перезапуск не создаёт слепых повторений | B13; U2/Надёжность | R21,R22 | S3 |
| D09 | APPROVED | Git/CI/PR, многоуровневые тесты, независимая проверка, ограниченные исправления без ослабления тестов | B8; U2/Разработка | R23,R25,R26,R27 | S1,S3,S5 |
| D10 | APPROVED | Унифицированные адаптеры Codex и других провайдеров | B9; U2/Разработка | R24 | S3 |
| D11 | APPROVED | Аварийный контроль, независимые мониторинг/доступ/копии и проверка восстановления | B16; U2/Безопасность,Надёжность | R28,R30,R31,R32,R41 | S3,S4,S6 |
| D12 | APPROVED | Проверяемый разрешённый выпуск; безопасный откат приложения без автоотката необратимой миграции | B17–18; U2/Надёжность | R33,R34 | S6 |
| D13 | APPROVED | Бюджет 10 000 ₽ как ориентир, резервы максимума, три вида затрат, пороги и защищённые расходы | B14–15; U2/Бюджет | R35,R36,R37,R38,R39,R40 | S2,S3,S4 |
| D14 | APPROVED | Функциональная аналитика с происхождением и типами утверждений после MVP | U2/Мониторинг; U3/Исключения | R42,R43 | POST |
| D15 | APPROVED | Внешние проекты самостоятельны, подключения отдельно разрешаются; пауза автосервиса и запреты внешних действий | B20; A; P; U4 | R45,R46,R47 | S2,POST |
| D16 | APPROVED | Указанные границы MVP и проверяемый сквозной сценарий | U3 | R48,R49 | S1,S5 |
| D17 | APPROVED | 0B ограничен документацией; PR без merge | U1; U5–7 | R50 | 0B |
| D18 | OPEN | Версии среды и образов; требуется: Совместимость и поддерживаемые версии | OPEN_ASSUMPTIONS, область 1 | R09,R23 | S1 |
| D19 | OPEN | Границы модулей и владение данными; требуется: Контракты и карта владения | OPEN_ASSUMPTIONS, область 2 | R05,R10,R11 | S1 |
| D20 | OPEN | Библиотека очереди, доставка, отмена, идемпотентность; требуется: Протокол восстановления и повторов | OPEN_ASSUMPTIONS, область 3 | R21,R22,R29 | S2 |
| D21 | OPEN | Механизм изоляции, сеть, срок жизни и очистка; требуется: Проверяемая модель исполнения | OPEN_ASSUMPTIONS, область 4 | R16,R17,R18 | S3 |
| D22 | OPEN | Контракт адаптеров и стоимость провайдеров; требуется: Спецификация тестового адаптера | OPEN_ASSUMPTIONS, область 5 | R24,R36,R37 | S3 |
| D23 | OPEN | Идентификация владельца и подтверждения; требуется: Аутентификация двух каналов, формат действия, TTL и отзыв | OPEN_ASSUMPTIONS, область 6 | R12,R13,R28 | S2 |
| D24 | OPEN | Тарифы, курсы, неизвестные расходы и защищённый резерв; требуется: Модель бюджета, период и правила порогов | OPEN_ASSUMPTIONS, область 7 | R35,R36,R37,R39,R40 | S2 |
| D25 | OPEN | Классификация данных, секреты и хранение; требуется: Политика данных, выдачи и доступа | OPEN_ASSUMPTIONS, область 8 | R15,R18,R20,R32 | S1 |
| D26 | OPEN | VPS, независимые мониторинг/доступ/копии; требуется: RPO/RTO, независимость от компрометации | OPEN_ASSUMPTIONS, область 9 | R01,R28,R30,R31,R32 | S6 |
| D27 | OPEN | Релизы и совместимость БД; требуется: Критерии выпуска, миграции и отката | OPEN_ASSUMPTIONS, область 10 | R33,R34 | S6 |
| D28 | OPEN | Права будущих интеграций; требуется: Отдельное разрешение по каждому проекту | OPEN_ASSUMPTIONS, область 11 | R42,R43,R45,R46,R47 | POST |
| D29 | OPEN | Детальная приёмка MVP и базовый мониторинг; требуется: Сценарии, доказательства и численные критерии | OPEN_ASSUMPTIONS, область 12 | R06,R25,R26,R41,R48 | S5 |
| D30 | APPROVED | Контроль происхождения сборок и выпускаемых артефактов | U2/Безопасность | R51 | S6 |

D18–D29 не имеют выбранного варианта, владельца реализации, даты утверждения или свидетельства проверки. Ответственный за принятие — владелец проекта; технические варианты готовятся отдельным заданием. Выход: версионированное решение с источником согласования, областью действия и проверкой соответствующих R. До этого запись остаётся OPEN.

Изменение APPROVED требует явного согласования владельца, ссылки на заменяемую запись и новую версию. Новая запись не стирает историю и не расширяет права исполнителя. Принятых в 0B новых технических решений нет.

## Дополнение Stage 0C-1: восстановление истории

Таблица D01–D30 выше сохранена как baseline 0B. [Исторический реестр H](../history/stage-0c-1/HISTORICAL_DECISION_REGISTER.md) отдельно учитывает 13+13 пунктов A/B со статусом OWNER_APPROVED_SUMMARY из [SRC-0C1](../history/stage-0c-1/SOURCE_PACKAGE.md). H — ID восстановления, не исходные исторические номера. [Матрица](../history/stage-0c-1/RECONCILIATION_MATRIX.md) сохраняет связи с D/R и отмечает подтверждения, уточнения и расширения без дублирования решений.

D05/R12 теперь читаются вместе с H-A07: policy layer независим и детерминирован, AI не может его обходить. D11 дополнен H-A10: критические monitoring/emergency controls/audit history/backups не зависят от доступности AI-провайдеров. Механизмы D18–D29 остаются OPEN; историческая сводка не выбирает их за владельца. Новые D в 0C-1 не создаются. Package C вынесен в [операционное состояние](../architecture/INFRASTRUCTURE_STATUS.md), не в архитектурный счётчик.

## Дополнение Stage 0C-2: решения H-C/H-D

D01–D30 и прежние H-A/H-B сохранены. Новые 26 индивидуальных OWNER_APPROVED_SUMMARY записей находятся в [историческом реестре 0C-2](../history/stage-0c-2/HISTORICAL_DECISION_REGISTER.md), [SRC-0C2](../history/stage-0c-2/SOURCE_PACKAGE.md) и [матрице](../history/stage-0c-2/RECONCILIATION_MATRIX.md). Package D использует supplied IDs H-C, Package E — H-D; они не являются прежним операционным Package C/OPS-C.

D02 уточняется project graph/readiness/impact/primary priority, D05 — approval cards/risk, D09 — layered checks/independent AI review/bounded disagreements, D10 — provider capability differences, D12/D30 — exact staged releases/health/supply chain. D18–D29 не объявляются закрытыми: механизмы и [U2-01–U2-13](../history/stage-0c-2/CONFLICTS_AND_UNCERTAINTIES.md) остаются OPEN. Выбор graph DB, CI/signature format, provider/model, isolation и численных caps не произведён. Новых строк D нет.

## Дополнение Stage 0C-3: supplied monitoring/audit decisions

D01–D30 и их прежние статусы/строки не изменены. [Реестр H-E/H-F](../history/stage-0c-3/HISTORICAL_DECISION_REGISTER.md) содержит 13 monitoring и 16 approved audit-summary решений из [SRC-0C3](../history/stage-0c-3/SOURCE_PACKAGE.md); [матрица](../history/stage-0c-3/RECONCILIATION_MATRIX.md) связывает их с R/D/52 прежними H. Новых D нет.

D13 уточнён H-F01 hard ceiling и действием 70/90/100, D05 — actual permissions/default deny (H-F04), D06 — localization/prompt injection/environment controls (H-F02/H-F06/H-F10), D08 — ambiguous operations/concurrency/leases (H-F11/H-F12/H-F15), D11/D26 — offsite backup/watchdog/console path/compromise response без default permanent second VPS, D30 — exact source/dependency/artifact provenance H-F16.

Source-approved controls не равны выбору конкретных retry/TTL/RPO/RTO/retention значений, lock/secret/CI vendor или новой microservice architecture. D18–D29 не закрываются автоматически; [U3-01–U3-16](../history/stage-0c-3/CONFLICTS_AND_UNCERTAINTIES.md) отделяют нормы от деталей и evidence. Package G не является полным исходным аудитом или доказательством работоспособности.

## Дополнение Stage 0C-4: analytics и infrastructure planning

D01–D30 и их строки/статусы сохранены. [Новые H-G/H-H](../history/stage-0c-4/HISTORICAL_DECISION_REGISTER.md) из [SRC-0C4](../history/stage-0c-4/SOURCE_PACKAGE.md) связаны с R/D/H в [матрице](../history/stage-0c-4/RECONCILIATION_MATRIX.md); новых D не создаётся.

D14 получает future KPI/provenance/forecast/accounting/cohort/marketing requirements, не analytics MVP authorization. D18/D26 частично уточнены H-H02/H-H03 approximate sizing/initial Ubuntu LTS/pinned Compose/security подходом, не concrete versions или purchased spec. D26/U3-07 теперь имеют source-backed provisional RPO≤15min/RTO≤4h и WAL/PITR where feasible (H-H06), но feasibility/restoration evidence OPEN.

D25 получает controlled secrets broker **или equivalent mechanism** H-H05, не выбранный vendor/new standalone service; D03/H-H13 modular monolith и запрет convenience-only infra additions сохраняются. D13/H-F01/H-H07 — hard ceiling, историческое «ориентир» не permission. D29/A01 уточнены approved synthetic starting pattern H-H11, без утверждения полноты acceptance. Все остальные конкретные choices/evidence остаются [OPEN U4](../history/stage-0c-4/CONFLICTS_AND_UNCERTAINTIES.md).
