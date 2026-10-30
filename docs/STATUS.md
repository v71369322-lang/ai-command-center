# Текущий контекст и облачный handoff

Снимок на **28 октября 2026, 14:03 UTC**. Это контекст продолжения, не новое
разрешение доступа, расходов, merge или deployment. Перед работой сверять
актуальные HEAD/PR/CI; ниже указаны проверенные точки, не вечные значения.

Последующее дополнение 28 октября: [фактическая cloud-проверка проектов](projects/CLOUD_VALIDATION_2026-10-28.md).
LNAuto прошёл native Linux baseline (13 backend с PG / 28 frontend / 10 browser),
без изменения исходников. Ваниль: свежий Prisma checksum GET снова дал HTTP 403;
её полный C2 runtime остаётся BLOCKED. Ниже сохранён исходный metadata snapshot.

Дополнение **28 октября, 16:43 UTC**:
[Capital-Lab проверен в текущей cloud-сессии](projects/CAPITAL_LAB_CLOUD_CHECK_2026-10-28.md):
1414 backend passed / 13 skipped / 1 warning, 138 frontend passed,
настоящие HTTP/PG и build PASS, исходники не менялись.
LNAuto затем получил отдельный [Draft UI PR #1](https://github.com/v71369322-lang/LNAuto/pull/1),
`6eb27e105f976130b9a7975517fc90504bdb1f9f`, с успешным frontend CI;
код этого UI-пилота уже отличается от первоначального read-only снимка ниже.
LNAuto на VPS не развёртывался. Название CryptoLab пока не сопоставлено с
отдельным доступным repo; Capital-Lab не переименован. Ни один из этих результатов
не подтверждает действующий канал F33 или доставку новой версии Commander на VPS.

Следующая cloud-доработка: [главное меню Telegram](telegram/OWNER_MENU.md),
source/test checkpoint `974430a260cde68d4e75f50cfd73e2cee886bede`.
Четыре кнопки вызывают прежние readonly-команды; AI/расходы/CRM не включаются.
Локально 140 targeted / 105 infrastructure, Ruff/OpenAPI/TypeScript/Vite PASS.
Итоговые HEAD/полный CI этой отдельной ветки сверять в её Draft PR.
На VPS меню пока не доставлено; F33 по-прежнему требует reconciliation.

Следующая доработка поверх меню: [кнопки выбора проекта запроса](telegram/PROJECT_PICKER.md),
checkpoint `bbd4d08092a214ada2fd284b4905101b2085d18b`.
Локально 203 targeted / 105 infrastructure PASS; назначение остаётся метаданными,
source/version/delivery/audit checks сохраняются. Итоговый полный CI — в Draft PR
этой отдельной ветки. Это также ещё не обновление действующего бота/VPS.

Более позднее подтверждение **28 октября, вечер МСК**:
[реальный канал F33 проверен](https://github.com/v71369322-lang/ai-command-center/blob/c4aa5a8449ba1e9a57d3922160bae3ffb33ced70/docs/infrastructure/F33_LIVE_VALIDATION_2026-10-28.md).
Владелец установил службы через SSH; cloud GitHub job на brain1 вернул signed
SUCCEEDED, exact replay идентичен, неразрешённый пакет отклонён подписанным
bundle_not_approved. Ed25519 проверен в облаке. Профиль истекает **22:24:55 МСК**,
max_updates=0, сам не продлевается и не останавливает runner по expiry.
Это уточняет исторические unknown ниже; Telegram app остаётся на 316dc16.

Следующий отдельный этап — [F34: подготовка Telegram update](infrastructure/F34_TELEGRAM_UPDATE_PREPARATION.md).
Target application SHA b2e71fe. Новые operator tools готовят private staged
binding и требуют отдельного exact approval для apply.

Актуализация **29 октября, МСК**: [F34 применён владельцем на VPS](infrastructure/F34_LIVE_VALIDATION_2026-10-28.md).
Application b2e71fe, operator tools 364c5eb, live bundle a1cf9b0d…be9c8,
activation VERIFIED и F34_UPDATE_VERIFIED. Проверены Telegram capture/project
choice/readback нового №131179132 и старого №131179125; /coding_plan доступен.
Это owner-provided SSH logs + desktop Telegram Web, не прямой cloud host probe.
Новые запуски остаются остановлены; post-update coding cycle и iPhone acceptance
пока не выполнены. AI/CRM/paid APIs/public HTTPS не подключены. Исторические
описания прежнего VPS состояния ниже не заменяют этот более поздний результат.

Следующая ограниченная cloud-доработка — [снятие обычной остановки через Telegram](telegram/NORMAL_STOP_RESUME.md):
двухшаговый /resume и одноразовая owner button используют прежний F1 resume;
recovery/security/неопределённые исполнения остаются блокерами. Новая версия
на VPS не доставляется автоматически; текущая live b2e71fe этой команды не имеет.

Cloud continuation: [пакет доставки Telegram resume](infrastructure/TELEGRAM_RESUME_RELEASE.md)
закрепляет target bdc8cbc (PR #37, full CI SUCCESS:694 Python /1 warning,
отдельно143 infrastructure). Operator helper получает явно выбранный fixed
profile b2e71fe→bdc8cbc; старый default f34 сохранён. Prepare-only script требует
нового разрешения/точного operator SHA и создаёт отдельный кандидат, не update.
На VPS ничего не выполнено, нового host bundle digest пока нет. Владельцу вне
компьютера не требуется вводить команды или передавать credentials.

Следующий отдельный cloud-шаг — [сводка готовности в Telegram](telegram/READINESS_SUMMARY.md)
поверх PR #38. `/readiness` читает F1 control, очередь этого подключения и, если
доступен, локальный профиль первого эксперимента; отсутствие gateway config
честно остаётся unknown. Не выдаёт grants и не читает ключи, не меняет спорные
резервы. Локально126 targeted passed; полный итоговый CI — в отдельном Draft PR.
На текущем VPS b2e71fe этой команды нет. PR #38 по-прежнему доставляет только bdc8cbc;
новую функцию нельзя считать включённой в прежний закреплённый пакет.

Продолжение в облаке: [единый mobile-релиз Telegram](infrastructure/TELEGRAM_MOBILE_RELEASE.md)
позволяет подготовить один переход b2e71fe→d932baa с `/resume` и `/readiness`.
Application [PR #39](https://github.com/v71369322-lang/ai-command-center/pull/39)
имеет успешный CI:724 Python /1 warning, отдельно210 infrastructure. Новый
operator profile `telegram-mobile` явно выбирается; прежние default/profiles
сохранены. Локально280 infrastructure passed. Source archive/manifest — только
ignored cloud evidence; host candidate/image IDs пока отсутствуют. VPS не менялся,
старые approvals не продлевались. Финальный operator HEAD/CI — в отдельном Draft PR.

Следующий cloud-шаг: [офлайн preflight первого AI-эксперимента](f2-2/OFFLINE_PREFLIGHT.md)
проверяет локальный профиль без HTTP clients, Gateway/Store и чтения credential
files. Даже LOCAL_CHECKS_PASSED не подтверждает remote state или paid consent.
Закоммичен только disabled template; реальный запуск CLI дал ожидаемый BLOCKED,
0 external calls. Локально58 новых /338 infrastructure, отдельно16 существующих
pure F2.2 tests; поднаборы не складываются. Src/runtime/пакет PR #40 остаются
неизменными. Account/model/funding/GitHub App/repo/credential/ledger проверки и
окончательное разрешение живого эксперимента остаются отдельными gates.

## Command Center: исходники и проверки

Cloud checkpoint **30 октября, после отъезда владельца**:
[единый порядок продолжения первого AI-запуска](f2-2/LAUNCH_CHECKPOINT.md)
связывает сохранённые credentials/build с оставшимися financial/config/deployment/
paid gates. Owner offline inspect/новый plan operator8e60568 получены; результат
предложенной второй выдачи неизвестен. При возвращении сначала read-only сверка
обеих попыток, expiry и deployment, без повторного prepare. Длительные prerequisites
готовятся до нового часового token. В облаке изменяется только документация;
VPS/credentials/paid calls не затрагиваются, повтор всей установки не требуется.

Актуализация30октября2026: владелец подтвердил прежний live d932baaf и private
custody ключей; offline plan operator0476b4c получен, application a5d867c локально
собран без deployment. Одна выдача GitHub token вернула BLOCKED: receipt
03:09UTC содержит token_request_attempted=true, expires_at04:06:33UTC, но
token file отсутствует и точный post-response stage/error не сохранён.
Это owner evidence, не cloud host probe. Не повторять исходную попытку/не
удалять её журнал. [Разбор и исправление диагностики/candidate custody](infrastructure/FIRST_EXPERIMENT_GITHUB_TOKEN.md)
идут отдельным cloud PR поверх #47; runtime guard/release targets остаются прежними.
Новая выдача не выполнена, paid_calls=0; дополнительные credentials требуют
нового reviewed owner решения, а не повторного использования прежнего плана.

Следующее cloud-продолжение поверх PR #46 — [операторская подготовка GitHub token](infrastructure/FIRST_EXPERIMENT_GITHUB_TOKEN.md).
Offline plan связывает source/key identity/paths с одной scoped credential
операцией. Future prepare после owner approval выпускает токен только для
ID1438229730, проверяет его effective repository count/permissions/baseline и
сохраняет private0600 без подключения runtime. Unknown outcomes не повторяются.
Полное число repos установки не выводится из scoped token; отдельный false
сохраняется. Реальные credentials/API/VPS пока не использованы; app target и
release pins PR #46 не меняются. Итоговый operator SHA/CI — в отдельном Draft PR.

Следующее cloud-продолжение поверх PR #45 — [отмена первого эксперимента](telegram/EXPERIMENT_CANCELLATION.md):
`/cancel_experiment` вызывает прежний F1 cancel для UUID, закреплённого при
получении команды. Повтор/перезапуск не отменяют будущую или заменённую задачу.
Расходы, спорные резервы и запрет повторного provider вызова сохраняются;
CANCEL_REQUESTED не выдаётся за подтверждённую остановку. VPS не менялся.
Итоговые source/operator pins и clean-source CI — в отдельном Draft PR.

Следующее cloud-продолжение поверх PR #44 — [явные уведомления эксперимента](telegram/EXPERIMENT_NOTIFICATIONS.md):
owner `/watch_experiment` / `/unwatch_experiment`, consent в прежнем audit и
delivery через существующий collector/outbox, без новой task authority. По
умолчанию выключено; source/profile/task binding, semantic dedupe и no-resend
для неизвестных отправок сохраняются. Source/image/deployment требуют нового
закреплённого пакета, paid calls этим не разрешаются.

Следующее cloud-продолжение поверх PR #43 — [просмотр первого AI-эксперимента](telegram/FIRST_EXPERIMENT_STATUS.md).
`/experiment` читает одну фиксированную API-задачу и проверенные локальные
result/financial anchors без Gateway/HTTP client construction и ключей.
Сохранены строгая Telegram scope для обычных тестов, paid approval и F1 guards.
Уточнён status после billing settlement: SETTLED сохраняет неопределённость
результата и запрет повтора. Финальные source/PR/CI — в отдельной ветке;
на VPS ничего не применяется автоматически.

Следующий cloud-шаг после owner account setup —
[явный deployment profile первого AI-эксперимента](f2-2/DEPLOYMENT_PROFILE.md).
Прежний VPS profile отвергал F2 env/mounts/egress, поэтому сохранённые и проверенные
owner credentials ещё не означали подключение runtime. Новый opt-in binding
закрепляет config bytes и прежний profile hash, предоставляет config API/broker,
а keys/egress только broker. Default closed и F1/финансовые guards сохраняются.
Source/image build, новые host bundle/approvals и paid run этим не выполняются.
Владелец подтвердил model metadata HTTP200 и App5524444/installation176497504
identity/permissions/target binding; selected count, installation token, payment
upper bound и новый actual runtime profile остаются отдельными проверками.
Итоговые commit/PR/CI этого изменения сверять в его отдельной ветке.

Продолжение без owner SSH: [закреплённый AI-профиль в Telegram readiness](telegram/READINESS_SUMMARY.md).
Явный prepare flag добавляет readonly config в Telegram без ключей и новых сетей;
прежние bundles сохраняются. `/readiness` использует существующие локальные gates,
не выполняет удалённые проверки и не выдаёт grants. Новый application SHA требует
своего закреплённого пакета; target PR #42 не изменяется автоматически.

- Репозиторий: [v71369322-lang/ai-command-center](https://github.com/v71369322-lang/ai-command-center).
- Предшествующая реализация до этапа меню: [Draft PR #31](https://github.com/v71369322-lang/ai-command-center/pull/31),
  `feat/telegram-coding-demo`, `b2b57ba8ae52d8ae7629c13647f250d0d92cfae7`.
- [CI этого SHA](https://github.com/v71369322-lang/ai-command-center/actions/runs/40698783681):
  593 Python passed / 1 Starlette-httpx warning, отдельно 105 infrastructure passed.
  Проверен merge-ref `a0d24fcb794c809d97c590775e9d4dfe92c4e4fa` с базой PR #30.
  Последующий documentation-only PR имеет собственный HEAD/CI в GitHub.
- Базы: #31 → #30 (`4b2acb0462f217b599790989f1b9785b15d4cbfe`) →
  #29 (`b7a32cde4852ad030b3464420bfe12497edc8709`) → #28 и предшественники.
  Исправленный deployment #17 (`53565cc2ca232fb2cf6d6552a3ae04b462d92956`)
  является предком проверенной реализации. Эти PR не объединены в main.

Реальные Git-изменения, tests/repair, отдельный verifier, durable F1 очередь,
restart/recovery/watchdog/backup и Telegram service проверены в облаке.
AI/provider и PR в coding-сценарии — mock. Настоящие OpenAI/GitHub adapters
остаются отдельно разрешаемыми и по умолчанию закрытыми. Полная production
готовность и приёмка реальных CRM не подтверждены.

Навигация:

- [F1 runbook](f1/README.md), [F2](f2/IMPLEMENTATION.md),
  [F2.1 readiness](f2-1/READINESS.md), [первый AI-эксперимент](f2-2/EXPERIMENT_PLAN.md).
- [Очереди проектов в Telegram](telegram/PROJECT_QUEUE.md),
  [mock coding-команда](telegram/CODING_DEMO.md).
- [Ограниченный серверный канал](infrastructure/BOUNDED_OPERATIONS_CHANNEL.md),
  [возобновление F33](infrastructure/F33_RESUME_FROM_PHONE.md).
- Первоначальный облачный план сохранён отдельно в
  [PR #18, exact source](https://github.com/v71369322-lang/ai-command-center/blob/d757b0bd2d121d0868173267c7dfc8b00f299eb5/CLOUD-MIGRATION-PLAN.md).
  Он не потерян, но его исторические статусы не заменяют этот снимок.

## Что известно о VPS, а что не проверено сейчас

Первоначальная cloud-разработка не подключалась к VPS. Впоследствии владелец
выполнил F33 bootstrap через собственный SSH и разрешил временную диагностику;
настоящие GitHub runner jobs и подписанные ответы проверены в облаке (ссылка выше).
Прямого Cloud SSH не было. Ниже сохранены происхождение и ограничения результата.

Приложение на 176.12.75.135 было обновлено до
`316dc1615dea224bcf4bd595d87048d19820bd21`, Telegram live bundle
`0ee8a6023296fdacfe632c2f364c488b2564db399bfd15af357812e41004d64b`.
Владелец проверил реальное сохранение/чтение запроса и уведомление о
синтетическом тесте, в том числе с iPhone. Cloud PR #27–#31 этим автоматически
не доставлены. Парольный вход через SSH tunnel не равен публичному HTTPS/MFA.

На VPS подтверждены acc-control UID 1000 и acc-exec UID 1001, отдельные rootless
Docker. После возвращения владелец подтвердил отсутствие трёх enrollment paths,
неизменность live bundle, hash старого bootstrap и отсутствие регистрации runner.
По новому явному разрешению diagnostic profile установлен, зарегистрирован и
запущен. Три настоящих mailbox job проверили status/replay/denial; приложение
не обновлялось. Это не бессрочный доступ и не разрешение source build/update.
Не повторять bootstrap и не заменять policy/key/journal после expiry. Новая
точная операция требует собственного разрешения; CRM 206.223.246.79 не затрагивать.

## Три бизнес-проекта: проверен только GitHub-контекст

В исходном снимке проверены метаданные GitHub: доступность, private visibility, branches/refs,
открытые PR и Actions runs по известным точным SHA. Исходники, клиентские
данные, локальные Windows-копии и полнота переноса в первоначальном metadata-снимке не читались,
не сравнивались и не изменялись. Последующая отдельная read-only проверка
LNAuto и C2-блокера Ванили описана по ссылке выше; бизнес-данные и Windows-копии
по-прежнему не читались. GitHub-доступ Codex не означает подключение
этих репозиториев к runtime coding-agent Command Center.

| Проект | Private repository / ID | Снимок main | Отдельная работа в GitHub |
| --- | --- | --- | --- |
| Ваниль и Сахар | [Vanilla-Sugar-CRM](https://github.com/v71369322-lang/Vanilla-Sugar-CRM), `1435253397` | `6b4c79b6955d75ad33f97569cad47884248d5bbf` | [Draft PR #1](https://github.com/v71369322-lang/Vanilla-Sugar-CRM/pull/1), `cloud/c2-linux-runtime`, HEAD `6b0ca0d4d03d26aec4d6e7511b30e42ff63b8df8`, база main |
| LNAuto | [LNAuto](https://github.com/v71369322-lang/LNAuto), `1434161534` | `a339242387cd5729f252613d6a3d17cbafe00007` | В снимке только main, открытых PR нет |
| Capital Lab | [Capital-Lab](https://github.com/v71369322-lang/Capital-Lab), `1434576176` | `1b18e033e127b853fd95e32cab88053e719bfdab` | [Draft PR #1](https://github.com/v71369322-lang/Capital-Lab/pull/1), `codex/cloud-c2-linux-compatibility`, HEAD `0e1a16986baa5a217b2ec03d0db5146c51bb6f8a`, база main |

Actions API с фильтром exact head_sha вернул **0 runs** для всех трёх main SHA
и двух перечисленных PR HEAD. Это **не PASS**, не доказательство отсутствия
локальных проверок и не утверждение, что workflow-файлов нет. Build/tests,
санитизация всей истории и полнота импорта пока не подтверждены этим снимком.
Упомянутые PR только прочитаны как metadata: их diff не ревьюился и merge
не рекомендуется без отдельной проверки. Default main не назначен автоматически
рабочей базой поверх открытых migration PR.

## Как ускорять параллельную работу

1. До подтверждения облачной базы не редактировать параллельно исходную
   Windows-копию: иначе появятся две расходящиеся линии. Не удалять её — она
   остаётся источником для проверки полноты переноса. Можно собирать требования
   и описания ошибок без персональных данных, не меняя production.
2. Не требуется ждать полной готовности Command Center, чтобы разрабатывать
   уже перенесённый проект через облачный Codex. Это отдельная разрешённая задача
   выбранного репозитория; автоматическое управление им самим Commander ещё не готово.
3. Для первого такого задания проверить актуальные refs/контекст/границы переноса,
   выбрать правильный parent PR, подтвердить воспроизводимый build/test на
   синтетических данных. Не объявлять код полностью перенесённым по наличию repo.
4. Один проект и одна ограниченная задача на ветку/PR. Разные проекты могут
   развиваться параллельно в отдельных облачных задачах. Не смешивать credentials,
   рабочие директории, DB или production-доступ. В одной ветке не вести два
   независимых изменения одних и тех же файлов.
5. Обычная итерация с iPhone: репозиторий + задача + acceptance → проверенная база →
   отдельная ветка → tests → PR/CI → короткий отчёт. Windows не нужен для сборки
   или передачи уже доступного кода. Merge/deployment остаются отдельными действиями.

Приоритеты владельца: запустить сам Command Center; Ваниль и LNAuto — высокие
бизнес-приоритеты, Capital Lab — ниже. Это не разрешение начать изменения этих
проектов в текущем задании. Их код/PR/settings/CI не изменялись. Ближайший
ускоритель для следующей отдельно разрешённой project-задачи — подтвердить её
облачную базу и воспроизводимые тесты, затем брать маленькое MVP-изменение.

## Команды проверки Command Center

- `git status --short`, `git branch --show-current`, `git log -1` — исходная точка.
- `.venv/bin/ruff check src tests scripts infra/vps`
- `.venv/bin/python scripts/export_contract.py --check`
- `.venv/bin/pytest infra/vps/tests -q` — offline infrastructure suite.
- `npm ci --prefix web` и `npm run --prefix web build`
- `scripts/cloud_test.sh [tests/paths]` — требует подготовленных локальных
  синтетических PG/Redis и secret bindings; runtime-тесты требуют точных образов.
- `scripts/verify_cloud.sh` — полный clean-source контейнерный прогон; собирает
  образы exact SHA, выполняет security/dependency gates, Python, backup/recovery,
  watchdog/cancellation и Telegram/coding smokes. См. `.github/workflows/f1.yml`.

Не применять локальный compose runbook к VPS. Docker-среда, proxy/CA, registry
и свободный диск должны быть реально доступны; ограничения платформы не обходить.
Отсутствующие prerequisites перечислять, не подменять новым результатом старого CI.

В handoff каждой задачи сохранять repo/branch/base SHA, scope, изменённые файлы,
коммит/PR, команды и результаты, CI, неразрешённые внешние intents/резервы,
точные блокеры и один следующий безопасный шаг. Временный workspace не архив.
