# Первый AI-запуск: продолжение после перерыва

Снимок **30 октября 2026**. Этот документ объединяет следующий порядок работы;
исторические runbooks сохраняют происхождение доказательств. Сам снимок не
выдаёт разрешений, не подтверждает текущие credentials и не запускает задачи.
Владелец уехал от компьютера; продолжение в облаке не требует его SSH-команд.

## Сохранённая работа

| Что | Последнее подтверждение | Что потребуется при возвращении |
| --- | --- | --- |
| Действующий Commander | Owner SSH: deployment VERIFIED, application `d932baafce53c0748396abfc019cf81b931ebfec`, bundle `fcab8e820c978ff62c0fb22e78826c480f960af0416e3673552009c647c37755` | Сверить deployment journal и actual services; это историческое evidence |
| Исходники и новые образы | Owner build: application `a5d867cb734a4954926a4e77c71e6f5be217057c`, `FIRST_EXPERIMENT_IMAGES_BUILT_NOT_DEPLOYED` | Проверить clean source и immutable image IDs на обоих rootless daemons; пересборка нужна при отсутствующих/неверных образах |
| OpenAI key | Owner custody: UID1000,0600, private parent0700; прежний metadata GET200 | Сверить custody и актуальность доступа отдельно; metadata GET не является генерацией |
| GitHub App key | Owner custody: UID1000,0600; App5524444, installation176497504 и target binding проверялись | Сверить custody/identity перед credential operation; PEM остаётся на VPS |
| Synthetic repo | ID1438229730, seed main `a41d5fdf083fa0a162299b74ac9c155b58b140cb`, protected=true | Свежая проверка через runtime credential; прежние Codex reads относятся к другой identity |
| Исправленный operator | Owner checkout `8e605680d73e97365c29612c4d6d74c18bafd9c6`; [Draft PR #48](https://github.com/v71369322-lang/ai-command-center/pull/48), final CI SUCCESS | Использовать exact clean checkout; runtime images этим operator-only исправлением не менялись |

Ключи, App, репозиторий и исходники не требуется создавать повторно только из-за
перерыва. Их актуальность проверяется перед использованием. Ни новый application
deployment, ни настоящий AI-запуск пока не подтверждены.

## С чего возобновить SSH

Сначала read-only сверка существующих результатов. Последняя owner-команда
подтвердила offline inspection первой попытки и новый offline plan. Результата
предложенной дополнительной выдачи пока нет; её выполнение неизвестно.

- Первая попытка: `/home/acc-control/github-app-access/first-token-attempt`.
  Legacy receipt: `REQUIRES_INSPECTION_NO_RETRY`, credential не сохранён,
  recorded expiry **2026-10-30T04:06:33Z = 07:06:33 МСК**. Сначала сравнить
  server UTC с этой датой. Отсутствие local file не доказывает upstream отзыв.
- Предложенная вторая попытка: `/home/acc-control/github-app-access/second-token-attempt`.
  Проверить наличие каталога; если он есть, выполнить существующий offline
  `inspect`, затем сверить recorded expiry без вывода credential values.
  Если каталога нет, это не разрешение автоматически выполнить `prepare`.
- Operator checkout для этих checks:
  `/home/acc-control/first-experiment-release/operator-diagnostics`, exact SHA выше.
  Reviewed second plan: `50654acd60e8a283211431989cb9c5ec8fdd976c5b7d4f3b8263601ac46f01b6`.
  Срок прежней команды/согласования не продлевается этим документом.

| Наблюдение | Следующий шаг |
| --- | --- |
| `TOKEN_STORED_NOT_CONNECTED`, final file присутствует, срок ещё действует | Проверить scope/baseline evidence и остаток срока перед подготовкой binding |
| `REQUIRES_INSPECTION_NO_RETRY`, retained candidate присутствует и не истёк | По fixed stage/error решить, нужен ли существующий readonly `inspect --probe`; он не выпускает и не продвигает токен |
| Candidate отсутствует, истёк, повреждён либо исход выдачи неизвестен | Сохранить records, разобрать исход; дополнительная выдача — новое конкретное решение с новым plan/attempt/deadline |
| Deployment journal находится в промежуточной фазе | Сверить journal/activation/services прежде любого apply/retry |

Не удалять/переименовывать попытки ради повтора. Successful probe не создаёт
`installation.token`, не снимает NO_RETRY и не заменяет deployment approval.
Подробности: [credential runbook](../infrastructure/FIRST_EXPERIMENT_GITHUB_TOKEN.md).

## Что подготовить до следующего короткого окна доступа

1. **Закрыть финансовые неизвестные.** Владелец сообщил баланс $8; свежий баланс
   и применимые условия оплаты ещё надо подтвердить. Приблизительные70₽/$ дают
   ориентир, но не подтверждённую all-in границу с комиссиями/налогами. Известный
   публичный расчёт двух вызовов — $0.618432; свежий тариф и payment upper bound
   нужны до заполнения confirmed tariff/evidence. Повторно обсуждать историческую
   стоимость пополнения ради этого не требуется.
2. **Заранее проверить длительные локальные prerequisites.** Exact source,
   image revisions на control/execution daemons, место, private paths, tools,
   predecessor bundle и совместимость с данными проверяются до новой выдачи.
   Сборка уже выполнена; новый token не должен ждать повторной сборки без причины.
3. **Подготовить структуру config.** Использовать прежний IntegrationConfig,
   model `gpt-5.4-mini-2026-03-17`, context400000/output2048 и оба бюджета≤100₽.
   Не подставлять вымышленные confirmed prices или текущие evidence. Disabled
   template намеренно не проходит live/deployment preflight.
4. **Подготовить оставшиеся действия как одну последовательность.** Ссылки на
   будущий final credential, exact application/operator pins, проверяемые outputs
   и критерии остановки должны быть определены до выдачи. При изменении paths или
   source прежний digest плана не подходит.

GitHub installation token живёт примерно час. Его выдача относится к короткой
заключительной последовательности, когда остальные prerequisites готовы.
Перерыв может потребовать нового короткоживущего credential; это не повтор всей
установки, не автоматическое продление и не повод заново создавать App/ключи.

## Заключительная последовательность

1. После сверки попыток и отдельного решения о выдаче получить проверенный final
   credential непосредственно перед использованием. При отказе сохранить stage/
   HTTP status/boolean checks и разобраться без повторного POST.
2. Собрать immutable config с настоящими ссылками/evidence и сроками, включая
   GitHub expiry. Выполнить прежний [offline preflight](OFFLINE_PREFLIGHT.md).
   `LOCAL_CHECKS_PASSED` подтверждает только локальную согласованность; runtime,
   внешние проверки и окончательное paid approval остаются отдельными.
3. Подготовить один новый deployment candidate через существующий prepare/stage
   с `--release first-experiment-cancel` и явными config/OpenAI/final-token bindings
   плюс readiness opt-in. Этот profile включает предыдущие readiness/status/watch/
   cancel функции. Точный переход: `d932baafce53c0748396abfc019cf81b931ebfec` →
   `a5d867cb734a4954926a4e77c71e6f5be217057c`. Старые release targets не меняются.
4. Inspect candidate и current predecessor, получить exact candidate approval,
   затем существующие apply/postcheck. Нужен новый фактический candidate digest;
   сборка образов, offline plan и этот документ не являются таким digest.
5. Проверить актуальный runtime, F1 stop/recovery/ledger и все9 expiring gates.
   Dry-run должен соответствовать выбранным source/config; старый Telegram mock
   не подтверждает новый live profile. Изменение config bytes требует нового pin/
   bundle/inspect/approval, а не редактирования live файла.
6. Отдельно согласовать одну точную задачу, profile hash/version, срок и бюджет,
   затем первый paid запуск. `/resume` снимает только обычную остановку; ни он,
   ни `live_authorized` не заменяют task grant. Не оставлять разрешённый запуск
   ждать, пока истекает credential/evidence.
7. После доставки `/experiment` показывает фиксированную задачу;
   `/watch_experiment` включает её уведомления по явному выбору владельца;
   `/cancel_experiment` отзывает действия через прежний F1. `CANCEL_REQUESTED`
   не является доказательством физической остановки; спорные резервы сохраняются.

Применение остаётся через [deployment interlocks](DEPLOYMENT_PROFILE.md),
без ручного compose up, отключения TLS/AppArmor или публичной admin-панели.
Первый результат проверяется в выделенном synthetic repo, максимум два AI-вызова
и draft PR; реальная работа CRM этим экспериментом не запускается.

## Доказательства этого cloud checkpoint

Сверены implementation first-experiment gates, deployment binding validator,
все8 именованных release pairs и operator inspection semantics. PR #48 открыт,
draft/unmerged; его final HEAD `8e605680d73e97365c29612c4d6d74c18bafd9c6`,
[full CI40997379953](https://github.com/v71369322-lang/ai-command-center/actions/runs/40997379953)
и [offline CI40997379961](https://github.com/v71369322-lang/ai-command-center/actions/runs/40997379961)
успешны. Это предыдущие code checks, не новые VPS acceptance или live API evidence.
Текущий checkpoint меняет только документацию; приложение/образы/полномочия прежние.
