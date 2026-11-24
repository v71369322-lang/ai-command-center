# Jarvis 2.0: установлен assistant-only runtime

24 ноября2026. Stage1 согласован владельцем после аудита («Давай», затем
«Действуем дальше»). Последующее прямое поручение — самостоятельно подтвердить
возобновление через веб-версию Telegram. Paid AI, merge и необратимая очистка
не разрешались и не выполнялись. Этот handoff — docs-only продолжение от9351ba6,
не новый application release и не подтверждение CI для нового docs commit.

## Текущая версия и доказательства

- [Draft PR107](https://github.com/v71369322-lang/ai-command-center/pull/107), без merge.
- Source `9351ba678c4a908169cf76fba81dec4fd5e3bc10`.
- PR merge-ref `1a98d35817f5c97f3ad20f1cac8127629dd44567`; tree совпадает с HEAD:
  `91a1b4b40ff373c3dbfd32d268a1c95e89b908d6`.
- [Итоговый CI](https://github.com/v71369322-lang/ai-command-center/actions/runs/45351642302),
  attempt1 SUCCESS: приложение2529 passed/1 optional skipped; отдельно speech23 passed,
  source-pinned images, container smokes, independent replay, restore, Ubuntu probe.
  Infra1014 passed; повтор в отдельном
  [offline job](https://github.com/v71369322-lang/ai-command-center/actions/runs/45351642330)
  не суммировать. Dependency audit64 packages/0 advisories, npm0, Bandit medium/high0.
- Локальные focused проверки99 passed; дополнительный operator readiness helper11
  passed. Они пересекаются с CI: не складывать в единое число тестов.
- Deployment и activation: оба VERIFIED, purpose `assistant-only-update.v1`.
- Bundle `ac5542f56c0155560cd35050f3adf9fcae6efb76310437274b0d782543ba8331`.
- Preparation `d09a1e9084497bcb1266a5fe11ddaf996d2e5a9b749454710d9169483c321c31`.
- API image `sha256:71c049a700df0eb6688895e31fe631b1b66bb192cf65a1b080bbb8bd4b9852bf`.
- Speech image `sha256:db1061459e6788242ef3084820c622d84262211a58e88099e435052e1df138e0`.

## Что изменено

Сохранены PostgreSQL, Redis, API, Telegram и локальное распознавание речи. Всего5
постоянных контейнеров, без новых AI-агентов. Developer commands/routes, новые
F1 jobs, approvals/claim/retry и gateway authority запрещены immutable opt-in
`assistant_only: true`/`F1_ASSISTANT_ONLY=1`. Отказ относится и к старым pending
developer intents. Технические подсказки `/develop`, `/setup`, `/connection`
убраны из новых personal replies. Запись подтверждается как сохранённая во Inbox,
выбор раздела необязателен. В меню6 personal кнопок.

Остановлены worker, runtime-broker, watchdog. Их образы/данные сохранены.
Остановлены Jarvis-only root units: `acc-operations.timer`, `acc-operations-runner.service`,
`acc-prepare-fixed.path`, `acc-password-prepare-fixed.path`, `acc-telegram-prepare-fixed.path`.
Timer/runner отключены; static paths остановлены. Runner проверен: привязан только
к этому репозиторию, активного Runner.Worker не было. Исторические failed units
не перезапускались и не reset-failed.

Пустой rootless Docker UID1001 (`acc-exec`) остановлен/disabled. UID1000 control
daemon, users, secrets, SQLite, execution images и rollback artifacts сохранены.
Проверен реальный preflight и создан backup при отсутствующем UID1001 socket:
assistant обслуживание больше не зависит от execution daemon.

Работающие7 контейнеров других проектов и полный набор/состояния135 rootful
контейнеров совпали с исходным снимком. Rootful Docker и CRM VPS не изменялись.

Фактические проверки VPS: rootless/cgroup limits, exact images/source/env/mounts/
networks, отсутствие трёх developer services, Redis, Telegram health, финансовый
ledger и fresh exact voice profile/model. Loopback HTTP: `/api/health` без auth401;
developer POST `/api/simulator/commands`, `/api/tasks/missing/approve`,
`/api/project-inbox/plan`403. Никаких технических задач этими проверками не создано.

## Apply и reconcile: важная история

Apply вызван ОДИН раз. Telegram при первоначальном старте завершился exit1,
OOMKilled=false, с общим failed-closed сообщением. Точная первоначальная exception
не сохранена приложением; не выдавать конкуренцию за доказанную причину этого exit.
Независимый startup probe (settings, binding, leadership, schema, audit, настоящий
getMe) прошёл. Один start того же точного контейнера восстановил процесс.

Новый runtime уже работал; журналы оставались INTENT/DEPLOYMENT_ATTEMPTED.
Повторного apply не было. Все stock postchecks проходили отдельно, но reconcile
периодически падал на voice heartbeat assertion: heartbeat был СВЕЖИМ и exact,
однако `BUSY` после конкуренции за Control row, а assertion требует `PAUSED`.
Порог45s и обязательное PAUSED не ослаблялись.

Operator-only helper ограниченно ждёт исходную readiness-проверку: максимум45s
и не дольше existing exact approval window. Повторяет только точный read-only
heartbeat code; требует тот же revision/profile/model, paid=false, halt=true,
recovery=false и age0..45. Unknown/changed identity/control/freshness отвергает.
Не повторяет financial checks/transaction bodies/commit, не меняет heartbeat,
source, images или журналы вручную. Stock reconcile закрыл ОБА журнала после
прохождения исходных assertions. Нормализованный статус generic reconcile имеет
историческое название PLANNING_ACTIVATION_RECONCILED; purpose в receipt — assistant.

Helper SHA256 `1765aa117891df9c616be95c2a081290b343e99c80ebf1fb2cba41324463fa95`;
11 локальных safety/bounds tests. Это временный operator adapter, не shipped
обновление runtime9351ba6. Его code/hash/receipt сохранены в private release и
зашифрованной recovery delta. В штатный операторский путь ещё нужно перенести
проверяемое readiness ожидание.

Exit137 старых worker/watchdog появился во время согласованного compose stop;
OOMKilled=false. Не объявлять его новым OOM-сбоем. В проверенном kernel interval
новых OOM kills не было.

## Настоящий owner Telegram UI

Сначала browser automation была недоступна; позднее доступ появился. Через
авторизованный веб-чат боту действительно отправлен `/resume`, затем нажата
свежая кнопка владельца. UI показал успешное снятие остановки. Никакой поддельный
Update, owner grant или callback в БД не вставлялся.

Для этого bounded окна тот же voice-контейнер временно остановлен, чтобы BUSY
heartbeat не инвалидировал card. Автоматический guarded same-container restore
через120s предотвращал оставление сервиса выключенным; после подтверждения
контейнер запущен сразу. Image/source/profile не менялись.

Серверная проверка: OPEN epoch53, recovery=false; настоящий
`telegram_resume_card_consumed` exact935 наблюдён; active Tasks0; все4 исторические
ExternalAction COMPLETE/reserved0. Расходы/доступы не расширялись. В activation
`task_admission_resumed=false` оставлен как факт INSTALLER; позднейший owner UI
resume — отдельное событие, не повод переписывать receipt.

Операторское уведомление реально SENT; queue→delivery13.41s. Это не измерение
phone→bot round trip. Короткий цикл owner command/callback/reply проверен вживую.
Новый voice service работает и пишет fresh exact heartbeat (в том числе BUSY при
backpressure); phone voice→ASR→readback→save ещё не проверен: реальных voice requests0.
Не подменять эту приёмку локальными/mock тестами.

## Ресурсы и сохранность

Исходный замер8 контейнеров726.91MiB. Промежуточный замер5 контейнеров638.53MiB
(voice405.7MiB). Финальный после восстановления обычного режима:
API71.68, voice191.70, Telegram73.24, Redis3.289, DB91.96MiB — всего431.87MiB,
около295.04MiB меньше исходного замера. Это point-in-time Docker working set,
не гарантированная постоянная величина. Дополнительный эффект остановленных
host services в эту сумму не включён.

Диск: освобождено0байт; зависимости/образы/таблицы/пользователи не удалялись.
Выпуск создал временные build artifacts. Отдельный private cleanup proposal:
три никогда не активированных prototype release + три profile directories и6
неиспользуемых prototype image IDs. Current935, проверенные955/9f rollback,
общая модель, DB, secrets и backups исключены. Proposal НЕ является разрешением.
До любого удаления нужны archival copy предложенных каталогов, свежий backup,
проверка отсутствия references и новое конкретное подтверждение владельца.

## Backup и восстановление

Штатные encrypted DB backup/decrypt/checksum подтверждены. Реальный network-none
disposable PostgreSQL restore прошёл с полным audit anchor, без изменения primary;
512MiB/0.5CPU/128MiB tmpfs сохранены. Старый full json_agg сортировал весь журнал
и заполнял tmpfs; shipped935 использует SQL-literal keyset pages256 без ослабления
полной проверки цепочки.

Независимые копии на ПК владельца, вне Git, с закрытым ACL; ключ защищён DPAPI
CurrentUser, raw scratch удалён. Проверены расшифровка и вложенные dump checksums.

- Base recovery139755117 bytes, SHA256
  `333212c8ef2c00a150dcc8dc09a6d35bd90399f29df75b78129d2480d026e01d`:
  исходный model, secrets/config, current955 receipts, DB и Git bundle.
- Live935 delta6584528 bytes, SHA256
  `2c6cba70ff7c18c4c05e71cc830132e66a5c42a101321289c0979d45373f46b3`:
  exact935 config/profile/VERIFIED receipts/operator repairs, свежий DB backup,
  Git bundle; общая модель берётся из base. ОБЕ копии нужны для восстановления.

Это ручная проверенная offsite copy, не автоматический offsite timer. Stock
`offsite_verified=false` не подменялся. Full-host restore/RPO/RTO не доказаны;
OCI images не экспортированы в архив, на существующем VPS сохранены. DPAPI
требует текущую Windows учётную запись. Restore drill не восстанавливал primary.

## Оставшиеся ограничения и следующий ограниченный этап

1. Не называть Jarvis2 полностью готовым: это отключение developer runtime и
   сохранение приёма. AI понимание, динамический registry, полноценные tasks/notes,
   память, Google OAuth, mentorship/growth ещё не реализованы/не подключены.
2. Global full-audit scans/Control lock в poller остаются причиной задержек и BUSY.
   Нужен следующий ограниченный reliability/performance шаг с сохранением
   авторизации/аудита, а не увеличением времени SQL/снятием checks. Initial exit1
   требует нормальной safe diagnostics и испытания перезапуска.
3. В935 voice BUSY heartbeat ещё инвалидирует normal resume card: этот переход
   использовал явное временное quiet window. Не считать general resume race исправленным.
4. App services по-прежнему restart=no; автоматический whole-app boot и backup
   timer не установлены/не приняты. Нельзя обещать восстановление после reboot.
   Обычная backup quota256MiB и отсутствие retention/автоматической offsite доставки
   требуют отдельного завершённого решения; бессрочный5min timer переполнит квоту.
5. После этого — вертикальный MVP: текст/голос→Inbox/task/idea/note, project registry,
   поиск/завершение простым сообщением. Платную AI классификацию не включать без
   отдельного согласования модели, лимита и передачи данных. Не начинать все темы сразу.

Private VPS release `/home/acc-control/jarvis-assistant-9351ba6-release`, data
`/home/acc-control/f30/state`; защищённые receipts находятся вне чистого source.
Stock legacy rollback требует сначала вернуть UID1001 Docker, затем выполнить
совместимый exact rollback через interlocks. Ничего не восстанавливать поверх DB
вслепую; текущий migration hash/database image совпадают с955 и9f. Возврат старых
developer permissions/paid access из rollback не разрешён.
