# Предлагаемая последовательность реализации

Весь порядок имеет статус DERIVED, а не утверждённый календарный план. Только 0B разрешён текущим заданием. Имена S1–S6 — локальные технические пакеты; они не являются объявлением владельцем этапов 0C, 1 и т. п. Состав этапа 0C ещё OPEN.

| Этап | Цель | Зависимость | Результат и выходной контроль | Что блокирует |
| --- | --- | --- | --- | --- |
| 0B | Структурировать доступный контекст | Объединённый 0A | Восемь документов, связанные R/D, пробелы, проверенный PR без merge | Ревью владельца |
| 0C (OPEN) | Получить точное следующее задание | Проверка 0B владельцем | Уточнённые границы и перечень решений для следующего задания | История и приоритетные OPEN; нет разрешения кода |
| S1 | Контракты, границы, каркас разработки | Разрешение реализации после документального ревью | G1: структура, политики данных, версии, CI; никаких реальных интеграций | D18,D19,D25 |
| S2 | Состояние, допуск, журнал, бюджет и очередь | S1 | G2: синтетические задачи и отрицательные сценарии согласования/резервирования | D20,D23,D24 |
| S3 | Один ограниченный исполнитель | S2 | G3: адаптер, сверка таймаута, перезапуск, остановка и ограничения | D20–D25; отдельное разрешение платных вызовов |
| S4 | Telegram и мобильная панель | S2; S3 для результатов | G4: общее состояние и отчёты, пороги, базовые сигналы | D23,D29; безопасная выдача доступов |
| S5 | Сквозная приёмка | S3,S4 | G5: фактический результат, тесты нескольких уровней, независимая проверка | D29; свидетельства, а не заявления AI |
| S6 | Эксплуатационная готовность | S5; отдельно разрешённые ресурсы | G6: мониторинг извне, аварийный доступ, копии/восстановление, происхождение и откат | D26,D27; расходы/production отдельно разрешает владелец |
| POST | Независимые подключения и аналитика | S6; отдельное задание на каждый проект | G7: свои контракты, права, метрики и приёмка | D28; автосервис остаётся на паузе |

R распределены по [матрице G](../architecture/DEPENDENCY_MATRIX.md); критерии проверки — в [реестре](../requirements/REQUIREMENTS_REGISTER.md). Граница безопасности действует до любого внешнего действия, а не откладывается на финальную приёмку.

Для передачи в 0C нужны: рецензия владельца на 0B; полный исторический реестр и итоговый аудит; неизменяемый источник задания U; ответы либо явное откладывание D18–D29 с запретом зависимых действий; точный объём 0C и полномочия. Если история ещё недоступна, требуется явно ограниченный владельцем объём следующей работы, без заявления о полном покрытии 128 пунктов.

## Разрешённый документальный подэтап Stage 0C-1

Выше сохранена предложенная последовательность 0B, а не актуальное разрешение реализации. Владелец отдельным заданием [SRC-0C1](../history/stage-0c-1/SOURCE_PACKAGE.md) разрешил восстановление Foundation & Personal AI Assistant: 26 пунктов, сверку и отдельное сообщение об инфраструктуре. Это уточняет прежний OPEN о составе 0C только в рамках 0C-1; S1–S6 и Stage 0C-2 не разрешены.

Сведения [о купленном VPS](../architecture/INFRASTRUCTURE_STATUS.md) не являются выполнением S6 или разрешением настройки. Новые функции ассистента ещё не распределены по этапам (OPEN U09); текущий порядок не используется для их исключения или автоматического включения в MVP.

Следующий вход и точные темы сверки описаны в [handoff](../history/stage-0c-1/NEXT_PACKAGE_HANDOFF.md). После документационного PR работа останавливается до следующего задания владельца.

## Разрешённый документальный Stage 0C-2

Получено отдельное задание [SRC-0C2](../history/stage-0c-2/SOURCE_PACKAGE.md): восстановить Project Management & Autonomous Development на базе коммита 0C-1 `301b07de174ad0da049813a24ede64dc3f4a04d0`. Прежние фразы о невыданном 0C-2 сохранены как историческое состояние; новое разрешение касается только 26 индивидуальных записей, сверки, impact, проверок документации и PR.

Порядок S1–S6 не разрешён, implementation не начинается. [Impact](../history/stage-0c-2/IMPACT_REPORT.md) и дополнение [dependency matrix](../architecture/DEPENDENCY_MATRIX.md) — DERIVED связи будущих prerequisites, не новый утверждённый план. Key milestones/MVP/production требуют owner acceptance H-C12, production exact release и health — H-D09; текущего deployment разрешения нет.

Ветка 0C-2 основана на 0C-1, PR в main наследует не объединённые PR #2/#3. Различие file counts по comparison bases объясняет [coverage report](../history/stage-0c-2/COVERAGE_REPORT.md). После документационного PR — остановка; [handoff 0C-3](../history/stage-0c-2/NEXT_PACKAGE_HANDOFF.md) не разрешает начало следующего этапа.

## Разрешённый документальный Stage 0C-3

Отдельный [SRC-0C3](../history/stage-0c-3/SOURCE_PACKAGE.md) разрешил Monitoring, Security & Recovery от `c8ebedaed996753e10e0c370cffe807b50908298`. Импортируются 29 individual H, сверка, impact, проверки Markdown и PR, **не S1–S6, preflight, VPS access или implementation**. Прежние тексты о ещё не заданном 0C-3 сохранены как historical state.

H-F14 — gate перед любым future server deployment/production, не только перед G6; реальная проверка provider access/legal/region/cost сама требует отдельной авторизации и сейчас запрещена. H-E06/H-F03 planned recovery не tested recovery, production restore owner-approved, H-F16 release exact approved artifact. Эти нормы не являются планом запуска сервисов в этом задании.

Новые scope/dependencies описаны как DERIVED в [impact](../history/stage-0c-3/SECURITY_AND_RECOVERY_IMPACT.md); [coverage](../history/stage-0c-3/COVERAGE_REPORT.md) объясняет comparison bases. Main и PR #2/#3/#4 не меняются/не объединяются. После documentation-only PR — остановка; [handoff](../history/stage-0c-3/NEXT_PACKAGE_HANDOFF.md) не разрешает 0C-4 или programming.

## Разрешённый документальный Stage 0C-4

Отдельный [SRC-0C4](../history/stage-0c-4/SOURCE_PACKAGE.md) разрешил Business Analytics & Infrastructure от exact `ef2ed801cc5760e9a700567958e5b8f1f9d2f863`: source/register/matrix/coverage/uncertainties/impact/handoff и documentation PR. Прежние фразы о ещё не заданном 0C-4 сохранены исторически; S1–S6/development/infra access/paid actions не разрешены.

H-H11 задаёт isolated synthetic E2E как future initial validation; real projects/data — separate secured pilot authorization. Full analytics остаётся вне MVP. Capital Lab/CRM кондитерской — independent potential pilots, автосервис PAUSED. [Impact](../history/stage-0c-4/ANALYTICS_AND_INFRASTRUCTURE_IMPACT.md) задаёт DERIVED dependencies KPI/source/permission/feasibility, не implementation plan.

H-H02/H-H03 initial sizing/OS family/security и H-H06 provisional RPO/RTO targets не означают server readiness или tested restoration. H-F14 preflight перед любым future deployment, H-H10 exact production release approval/health/safe rollback и no auto-reverse irreversible migrations сохраняются; preflight сейчас запрещён. [OPS-C](../architecture/INFRASTRUCTURE_STATUS.md) не проверяется.

Ветка основана на 0C-3, PR в main наследует не объединённые #2/#3/#4/#5; [coverage](../history/stage-0c-4/COVERAGE_REPORT.md) различает file counts. После PR остановиться; [handoff](../history/stage-0c-4/NEXT_PACKAGE_HANDOFF.md) не разрешает 0C-5/software development.
