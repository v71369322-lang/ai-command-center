# Текущий контекст и облачный handoff

Снимок на **28 октября 2026, 14:03 UTC**. Это контекст продолжения, не новое
разрешение доступа, расходов, merge или deployment. Перед работой сверять
актуальные HEAD/PR/CI; ниже указаны проверенные точки, не вечные значения.

## Command Center: исходники и проверки

- Репозиторий: [v71369322-lang/ai-command-center](https://github.com/v71369322-lang/ai-command-center).
- Последняя проверенная реализация: [Draft PR #31](https://github.com/v71369322-lang/ai-command-center/pull/31),
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

**Ни одного нового подключения к VPS эта облачная работа не выполняла.**
Ниже — последние предоставленные владельцем результаты, не текущий health probe.

Приложение на 176.12.75.135 было обновлено до
`316dc1615dea224bcf4bd595d87048d19820bd21`, Telegram live bundle
`0ee8a6023296fdacfe632c2f364c488b2564db399bfd15af357812e41004d64b`.
Владелец проверил реальное сохранение/чтение запроса и уведомление о
синтетическом тесте, в том числе с iPhone. Cloud PR #27–#31 этим автоматически
не доставлены. Парольный вход через SSH tunnel не равен публичному HTTPS/MFA.

На VPS ранее подтверждены acc-control UID 1000 и acc-exec UID 1001, отдельные
rootless Docker. После попытки установить новый канал F33 последнее read-only
сообщение было `enrollment_files_present=false`; результат последующего
исправленного install-блока не получен. Текущее наличие файлов/регистрация/
активация **неизвестны**. Установочное окно до 14:58 МСК 28 октября истекло.
Автопродления, перезаписи или новой регистрации без сверки не выполнять.

Владелец пока вне дома. Серверные действия приостановлены. После возвращения
первый шаг — одна read-only проверка из F33 handoff, затем точное продолжение
по фактическому состоянию. Не обещать рабочий постоянный канал или доставку
новой версии до доказанного результата. VPS CRM 206.223.246.79 не затрагивать.

## Три бизнес-проекта: проверен только GitHub-контекст

Проверены метаданные GitHub: доступность, private visibility, branches/refs,
открытые PR и Actions runs по известным точным SHA. Исходники, клиентские
данные, локальные Windows-копии и полнота переноса в этой задаче не читались,
не сравнивались и не изменялись. GitHub-доступ Codex не означает подключение
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
