# Следующий релиз: normal-stop resume из Telegram

Цель — доставить уже реализованную функцию PR #37, не расширяя набор возможностей.
VPS в этом этапе не изменяется. Подготовка будущего host-кандидата и его применение
требуют отдельных свежих разрешений; прежние F33/F34 окна истекли.

## Закреплённые версии

- Последний owner-provided VPS source: `b2e71fe073f3109e639dac43496884905ce86d9f`.
- Последний VERIFIED live bundle:
  `a1cf9b0d783cc15a17e8d119167008a81584a051bcd55a0e9b359c519d8be9c8`,
  active directory `/home/acc-control/f34/candidate`.
- Application target: `bdc8cbcdcf3fe2377fa6cc08250c331d35f99f82`,
  [PR #37](https://github.com/v71369322-lang/ai-command-center/pull/37).
- Его [полный CI](https://github.com/v71369322-lang/ai-command-center/actions/runs/40815533520)
  SUCCESS: 694 Python /1 прежний warning, отдельно143 infrastructure. Проверен
  merge-ref44a34d9f1bea6c30d22b9b305388966291d0abec; это не merge PR.
- Новый operator helper SHA — final HEAD отдельного PR с этим документом.
  Он не является application target; исходники приложения остаются bdc8cbc.

Сравнены точные Git blobs b2e71fe → bdc8cbc: models.py/admin.py, requirements.lock,
uv.lock, Dockerfile/Dockerfile.executor, compose.yaml и web/package-lock.json
одинаковы. Новая DDL/migration, пакеты и смена daemon boundary не нужны.
Git-история требуется для этого теста; offline CI теперь делает fetch-depth=0
при прежних contents:read и persist-credentials:false.

## Изменение инструмента

`stage_telegram_update.py --release telegram-resume` выбирает только этот
фиксированный source pair. `--release f34` и старый default сохраняют прежний
316dc16→b2e71fe переход. Автоматического выбора по manifest нет, произвольные
SHA/latest/main/новые repo не принимаются. Selection не заменяет exact old/new
bundle digests и временное разрешение apply.

Те же проверки schema/DB/Redis/UID/data-root/login/owner/bot, source/image
pinning, VERIFIED predecessor, production connection binding, deployment.lock,
pause/backup/update/postcheck и durable no-retry activation journal сохранены.
Release name добавляется в staging/activation journal для reconciliation, но
сам plan не становится источником полномочий. Source/profile mismatch падает
до изменения live state. Runtime grants и F33 protocol не меняются.

## Будущий запуск при доступе к VPS

1. Сначала read-only сверить текущие deployment.json, active directory и службы.
   Не считать сохранённые здесь owner logs сегодняшним health probe.
2. Получить новое ограниченное разрешение только на source fetch/build/stage.
   Под acc-control загрузить operator checkout по точному окончательному SHA
   этого PR, с прежним отдельным ACC read-only deploy key и pinned known_hosts.
   Ни паролей, ни приватного ключа, ни Bot token в чат не передавать.
3. Из этого clean checkout выполнить `bash infra/vps/prepare_telegram_resume.sh`.
   Обязательные trusted параметры: `ACC_OPERATOR_REVISION=<exact helper SHA>` и
   `ACC_PREPARE_APPROVED_UNTIL=<согласованный абсолютный Unix deadline, max2h>`.
   Примеры со старым/автоматически продлеваемым deadline не выдаются за разрешение.
4. Script требует UID1000/brain1, прежний exact VERIFIED predecessor и25GiB
   свободного места. Не создаёт пользователей/ключи/службы, не ставит пакеты,
   не меняет Docker/AppArmor/firewall. Новый private workspace:
   `/home/acc-control/telegram-resume-release`; существующий не перезаписывает.
5. Script получает только application bdc8cbc из фиксированного ACC repo,
   проверяет clean checkout/lock, использует существующий build_release.sh для
   двух rootless daemons, делает disabled prepare и именованный live stage.
   Success marker: `TELEGRAM_RESUME_CANDIDATE_PREPARED_NOT_APPLIED`.
   Последний JSON содержит **реальный** candidate bundle digest после host build;
   cloud не подставляет фиктивные image IDs или заранее выдуманный digest.
6. Затем отдельно согласовать old/new digests и свежий apply deadline max1h.
   Под acc-control, с PYTHONPATH нового application/src, вызвать:

```text
tools-python exact-operator/infra/vps/stage_telegram_update.py apply --release telegram-resume --active-bundle /home/acc-control/f34/candidate --output /home/acc-control/telegram-resume-release/candidate --approved-previous a1cf9b0d783cc15a17e8d119167008a81584a051bcd55a0e9b359c519d8be9c8 --approved-candidate EXACT_HOST_CANDIDATE --approved-until EXACT_NEW_DEADLINE
```

7. Сверить activation/deployment VERIFIED, postcheck и source. Не возобновлять
   admission автоматически. В Telegram: `/resume` → свежая owner button →
   подтверждённый ответ → ровно один `/coding_demo` → реальные тесты/repair/
   independent verifier с mock provider → Telegram result, mock PR без публикации.
   В конце согласованного теста `/stop` снова закрывает admission.

Подготовительный script можно запустить в bounded transient service, как в F34,
после новой авторизации. Это удержит процесс при разрыве SSH. Его deadline и
ограничения клиентов не обещают автоматической остановки Docker BuildKit daemon;
CPU/RAM ограничения исполняемых задач остаются в прежнем runtime policy.

При ошибке/response loss сохраняются prepare.log, новые directories, images и
оба deployment/activation журнала. Не повторять команду, не удалять marker,
не делать автоматический binding rollback. Сначала reconciliation фактического
состояния. Старые immutable images/предыдущий config/backup сохраняются; их
наличие само по себе не доказывает выполненный откат или offsite recovery.

## Что реально проверяется в облаке

Вся прежняя stage/apply матрица выполняется для обоих fixed profiles на private
файлах с **fake engines/Deployment**, включая unknown source/scope, races,
deadlines, locks, uncertainty/no-retry. Compose config настоящий, без daemon.
Дополнительно проверены wrong/default/unknown profile до IO, CLI propagation,
скриптовые запреты без разрешения/точного operator SHA, bash syntax, неизменность
закреплённых schema/dependency/boundary blobs.

Локально: infra/vps/tests + tests/test_deployment.py — **278 passed /1 прежний
Starlette/httpx warning**. Новая матрица staging —105 cases; предыдущая38 входит
в неё, повторно не суммируется. Infra отдельно теперь210 cases, входит в278.
Ruff/OpenAPI/TypeScript/Vite/security/dependency checks PASS:64 Python packages,
0 Python/npm advisories,0 Bandit MED/HIGH,84 reviewed LOW. Финальный полный CI
operator HEAD проверяется отдельно в PR; предыдущий CI #37 — только application
target evidence и не подменяет новый результат.

Полный positive запуск shell script на brain1 и rootless build/stage/apply нового
target не выполняются здесь. Шаблон не считается реально созданным host bundle.
Новые source archives/manifest можно подготовить только как ignored cloud
artifacts; они не Git release и не публичная ссылка для скачивания. Доставка
исходников по-прежнему из private GitHub прямо на VPS, без Windows/images.tar.

Реальные AI, voice, API keys, расходы, CRM, публичная web-панель и production
не включаются. Для первого AI эксперимента остаются отдельные credentials,
подтверждение модели/тарифа/бюджета, synthetic repo/GitHub App scope и финальное
разрешение; 100 ₽ не является автоматическим разрешением списания.
