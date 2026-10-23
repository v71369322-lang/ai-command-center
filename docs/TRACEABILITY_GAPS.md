# Пробелы прослеживаемости

Версия 0B.1. Полный текст 128 ранее утверждённых пунктов не получен. 51 агрегированное требование R01–R51 и 18 APPROVED-записей D отражают только доступный контекст. 12 OPEN-записей не являются решениями. Нельзя утверждать покрытие 51/128: единицы и исторические номера несопоставимы. Фиктивных записей до 128 нет.

Доступная база: main после PR #1, коммит `9eb98cb3020db942cbd9a1377b9ccd3a34d2316e`; AGENTS.md, PROJECT_OVERVIEW.md, ARCHITECTURE_BASELINE.md, OPEN_ASSUMPTIONS.md; задание U на 0B из текущей сессии. Полный текст U в репозитории не сохранён; разделы и предметные ссылки перечислены в реестре R. Это частичная прослеживаемость, а не исторический архив.

| ID | Статус | Чего нет | Затронутые связи | Что нужно получить / выход |
| --- | --- | --- | --- | --- |
| GAP01 | OPEN | Полного текста, исходных ID и редакций 128 пунктов | Все R/D; историческое покрытие неизвестно | Оригинальный реестр с источниками утверждения; таблица исторический ID → R/D либо обоснованный пробел |
| GAP02 | OPEN | Полного исторического реестра решений, альтернатив и замен | D01–D30 | Оригинальные решения с датами/версиями, отменами и согласованиями; сопоставить без перезаписи истории |
| GAP03 | OPEN | Итогового аудита, обещанного в 0A | Все границы, приёмка | Полный аудит и замечания; создать отдельные связи к R/D и план закрытия |
| GAP04 | OPEN | Стабильного репозиторного первоисточника задания U | R с U, новые против 0A принципы | Предоставить оригинал/экспорт задания с датой и версией для точных ссылок; не выдумывать номера исторических пунктов |
| GAP05 | OPEN | Утверждённых технических ответов 0A | D18–D29 | Ответы владельца по OPEN_ASSUMPTIONS, выбранные варианты, ограничения и доказательства |
| GAP06 | OPEN | Численных SLA, RPO/RTO, TTL, времени/попыток/параллельности, защищённой суммы и правил расчёта порогов | R08,R13,R28,R30–R40 | Определить до зависимой реализации; нынешние критерии описывают поведение без фиктивных чисел |
| GAP07 | OPEN | Детальных контрактов, модели угроз, формата provenance и протоколов приёмки | R10–R34,R48,R51 | Версионированные контракты, сценарии сбоев и доказательства; решения с отдельным согласованием |
| GAP08 | OPEN | Утверждённого задания и границ 0C | Последовательность S1–S6 | Ревью 0B и отдельное задание владельца; не начинать реализацию автоматически |

Процедура пополнения (DERIVED): сохранить первоисточник и версию → сопоставить каждый исторический пункт → явно выделить совпадения, уточнения, конфликты и непокрытые пункты → передать конфликты владельцу → обновить R/D/зависимости/проверки с историей изменений. Ни пропуск, ни молчание не отменяют APPROVED.

A01 (ASSUMPTION): синтетической задачи без клиентских данных достаточно для первого сквозного теста. Это предложение сценария, а не утверждённый критерий полноты MVP; подтверждение требуется в D29. Записано также в [OPEN_ASSUMPTIONS](OPEN_ASSUMPTIONS.md).

Проверки 0B ограничены документами и доступными источниками. Успешное ревью этих материалов не доказывает историческую полноту, безопасность реализации или работу инфраструктуры.

## Прогресс Stage 0C-1

Предыдущие GAP01–GAP08 сохранены как baseline 0B. Получен [SRC-0C1](history/stage-0c-1/SOURCE_PACKAGE.md): 13 пунктов foundation и 13 personal assistant; все индивидуально импортированы в [H-реестр](history/stage-0c-1/HISTORICAL_DECISION_REGISTER.md) и [сверены](history/stage-0c-1/RECONCILIATION_MATRIX.md). Это частичное дополнение GAP01/GAP02, не закрытие полного исторического реестра, исходных дат/ID/транскриптов или итогового аудита GAP03.

GAP04 касается задания U этапа 0B и остаётся OPEN: сохранение текста нового источника SRC-0C1 не восстанавливает старый первоисточник. GAP05–GAP07 сохраняются в части механизмов/доказательств. GAP06 частично уточнён H-B03/H-B04 (local quiet hours и report times), но timezone, доставка и прочие численные цели остаются OPEN. Для GAP08 получено точное документальное задание 0C-1, а не разрешение S1–S6 или 0C-2.

[Покрытие](history/stage-0c-1/COVERAGE_REPORT.md): 26/26 пунктов этого пакета, 0 пропусков, 0 точных дубликатов, 0 подтверждённых конфликтов, 12 групп OPEN. 51 агрегированное R и 30 D не равны числу исторических решений. [Package C](architecture/INFRASTRUCTURE_STATUS.md) — одно отдельное обновление состояния с пятью положениями; в 26 и в счёт архитектурных утверждений не включается. Новых ASSUMPTION нет; прежнее A01 остаётся непроверенным.

## Прогресс Stage 0C-2

[SRC-0C2](history/stage-0c-2/SOURCE_PACKAGE.md) добавляет supplied Packages D/E: H-C01–H-C13 и H-D01–H-D13. [Register](history/stage-0c-2/HISTORICAL_DECISION_REGISTER.md), [matrix](history/stage-0c-2/RECONCILIATION_MATRIX.md) и [coverage](history/stage-0c-2/COVERAGE_REPORT.md): 26/26 индивидуально, 4 CONFIRMS, 14 REFINES, 8 EXTENDS, 0 missing/exact duplicates/confirmed conflicts. 13 групп OPEN U2-01–U2-13 и 0 новых ASSUMPTION.

GAP01/GAP02 теперь частично дополнены двумя тематическими пакетами (52 unique H records), не закрыты. Это не 52 уникальных исходных решения и не доля 52/128; R/D остаются агрегированными и не суммируются с H. Original transcripts/timestamps/IDs/approvals/alternatives/implementation evidence для новых 26 не переданы.

GAP03/GAP04 по аудиту/источнику 0B не закрыты. GAP05–GAP07 по mechanisms/numerical limits/contracts/evidence остаются OPEN. GAP08 уточнён отдельным documentation-only заданием 0C-2, не разрешением S1–S6 или 0C-3. Старый отчёт 0C-1 U10 сохранён как исторический: тема 0C-2 теперь известна, тема 0C-3 нет. [OPS-C infrastructure status](architecture/INFRASTRUCTURE_STATUS.md) не менялся; VPS purchased, access impairment reported, no readiness evidence/access/configuration/deploy.

## Прогресс Stage 0C-3

[SRC-0C3](history/stage-0c-3/SOURCE_PACKAGE.md) содержит 13 H-E monitoring + 16 H-F approved audit-summary решений. [Register](history/stage-0c-3/HISTORICAL_DECISION_REGISTER.md), [matrix](history/stage-0c-3/RECONCILIATION_MATRIX.md), [coverage](history/stage-0c-3/COVERAGE_REPORT.md): 29/29 individual source/register/matrix, 2 CONFIRMS / 18 REFINES / 9 EXTENDS, 0 missing/exact duplicates/confirmed conflicts. 16 OPEN-групп U3-01–U3-16, 0 новых ASSUMPTION. Все 52 прежних H и R/D сохранены.

GAP01/GAP02 частично дополнены тремя тематическими пакетами, всего 81 H record, не 81 уникальное оригинальное решение и не 81/128 coverage. Original transcripts/dates/IDs/alternatives/approval trails новых 29 отсутствуют. GAP03 теперь частично дополнен 16 owner-approved audit-summary решениями Package G, **но полный исходный аудит и execution evidence не получены**.

GAP04 source 0B не восстановлен; GAP05–GAP07 уточнены нормами, но concrete mechanisms/численные limits/contracts/test evidence остаются OPEN. Из старого baseline по RPO/RTO найдены только OPEN упоминания, targets ≤15 min/≤4 h не найдены; условное правило нового source не устанавливает значения или гарантии. GAP08 получил ограниченную тему 0C-3, не разрешение кода/0C-4.

[OPS-C status](architecture/INFRASTRUCTURE_STATUS.md) не менялся: VPS уже куплен по сообщению владельца, console impairment reported, readiness unknown. H-F14 preflight требуется перед future deployment, но в этом этапе **не разрешён**. Planned recovery/test requirement не operational proof; original A01 не подтверждён synthetic default H-F10.

## Прогресс Stage 0C-4

[SRC-0C4](history/stage-0c-4/SOURCE_PACKAGE.md), [register](history/stage-0c-4/HISTORICAL_DECISION_REGISTER.md), [matrix](history/stage-0c-4/RECONCILIATION_MATRIX.md), [coverage](history/stage-0c-4/COVERAGE_REPORT.md): 13 H-G + 13 H-H = 26/26, 8 CONFIRMS/10 REFINES/8 EXTENDS, 0 missing/exact duplicates/confirmed conflicts. 16 OPEN groups U4-01–U4-16, 0 новых ASSUMPTION.

81 прежний H и history packages сохранены; теперь 107 H records, не доказанное число уникальных original decisions и не fabricated percentage unavailable register. R/D/OPS-C строки/исторические статусы не изменены. Source section 2 operational/access/Ytimes-storefront constraints имеют anchors и отдельные supplemental links, не фиктивные дополнительные H.

GAP01–GAP04 по original transcripts/IDs/dates/approval trails/full register/audit/source 0B не закрыты. GAP05–GAP07 получают explicit planning norms H-H02/H-H03 и **provisional** RPO≤15min/RTO≤4h H-H06, но concrete versions/actual spec/legal/data matching/feasibility/restore evidence OPEN. Прежний 0C-3 поиск корректен для его baseline; новый source даёт targets, не retrospective guarantee.

H-H11 owner-backed synthetic starting pattern не превращает A01 в acceptance proof. [OPS-C](architecture/INFRASTRUCTURE_STATUS.md) всё ещё reported purchased/impaired console, unverified config/security/readiness/current billing; FirstVDS planning context не actual provider selection. GAP08 получил отдельное documentation-only задание 0C-4, не 0C-5/development/server/preflight permission.

## Stage 0C-5: current audit, не доказательство original completeness

[SRC-0C5](history/stage-0c-5/SOURCE_PACKAGE.md), [31 records](history/stage-0c-5/HISTORICAL_DECISION_REGISTER.md), [matrix](history/stage-0c-5/RECONCILIATION_MATRIX.md), [coverage](history/stage-0c-5/COVERAGE_REPORT.md): 30 H-I + 1 H-J, 31 exact mappings, 5 CONFIRMS/18 REFINES/8 EXTENDS, 0 missing/exact duplicates/confirmed owner conflicts. Prior 107 и все packages preserved; now 138 supplied H, не exact original count/процент unavailable register.

[Final audit](history/stage-0c-5/FINAL_ARCHITECTURE_AUDIT.md) оценивает всю доступную базу и готов для owner review с gaps. GAP01–GAP04 original transcripts/IDs/dates/approval trails/register/исходный historical audit/0B source не закрыты новым available-document audit. Это разные объекты evidence, не fabricated восстановление оригинала.

GAP05–GAP07 нормализованы в [15 classified items](history/stage-0c-5/CONFLICTS_AND_UNCERTAINTIES.md): 1 CB/8 SG/3 NB/3 ME, не сумма старых U. PG durability/Git-vs-PG responsibility/web MFA/verified binding/OpenAPI/events/pilot read-only path source-backed, но concrete schema/versions/methods/evidence OPEN.

A01 и DERIVED G-order/blanket-OPEN blocking уточнены без перезаписи historical statuses. GAP08 теперь имеет только documentation/audit 0C-5 scope; exact next implementation envelope/authorization отсутствует. OPS-C file не менялся, no actual tests/readiness/evidence/current billing. Никаких новых ASSUMPTION/permissions.
