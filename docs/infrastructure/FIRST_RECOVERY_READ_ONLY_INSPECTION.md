# Возвращение к восстановительному тесту после паузы

Владелец 30 октября 2026 ушёл от компьютера и разрешил продолжить облачную
подготовку. Этот этап добавляет только операторскую диагностику и её проверки.
Он не выполняет предложенную ранее серверную сборку и не продлевает старые
разрешения или токены. Приложение восстановления остаётся закреплено на
`bf91c05c754ad41e7f89223ec8d05c02c9007de1`; переходы и build-only launcher из
[PR #58](https://github.com/v71369322-lang/ai-command-center/pull/58) не меняются.

## Один локальный отчёт

[inspect_first_recovery.py](../../infra/vps/inspect_first_recovery.py) предназначен
для существующего runtime-broker версии
`322186dc180257c618d8b159c78faa6e5bbf0b43`. Он не требует предварительного
обновления приложения, новых credentials или открытия сети. Скрипт объединяет
пять локальных наблюдений:

- фиксированная FAILED-задача `938e838d-54d4-470d-ad71-5c6a49a42c7d`, старый
  grant digest, расход и резерв, audit/action-ledger и классификация сохранённого
  ответа; текст модели и произвольные exception messages не выводятся;
- запись той же задачи/fence в runtime SQLite, DONE, имя контейнера, отсутствие
  незавершённых runs, свежесть worker/watchdog и целостность runtime evidence;
- существующий rootless/cgroup/systemd preflight и точный `docker ps -a` для
  контейнера этой задачи; ошибка daemon не считается отсутствием контейнера;
- hash старого защищённого профиля и соответствие original grant;
- актуальность девяти локальных evidence без вывода их references или ключей.

PostgreSQL использует `REPEATABLE READ, READ ONLY`; прежний Store.transaction с
`SELECT FOR UPDATE` не вызывается. RuntimeLedger constructor также не вызывается:
он мог бы создать или мигрировать SQLite. Reader открывает существующий private
regular single-link файл через read-only descriptor и `mode=ro`, включает
`query_only`, использует одну SQLite read transaction и прежние методы проверки
журнала. WAL отклоняется по header до открытия SQLite, чтобы не создавать SHM
sidecar. Никакой автоматической конвертации/ремонта журнала нет. Проблема чтения
не считается доказательством завершения.

Docker использует только существующий локальный Unix socket через прежний
RuntimeBackend. Только info/preflight и точный ps; нет stop/rm/run/exec внутри
диагностики, создания grants, heartbeat writes, reconciliation, token refresh
или provider HTTP. DB credential читается существующим Settings внутри trusted
broker; provider credential values диагностике не нужны и не читаются.

## Запуск позднее

Сначала нужен новый конкретный owner-approved read-only шаг для brain1 и
проверенная точная копия operator commit. Не пересылать сохранённый ответ,
ключи, token или config через чат. После проверки SHA скрипта оператор может
передать его в stdin уже работающего broker через локальный Docker exec:

```sh
# Template only: run on brain1 after authorization and exact operator checkout.
cd /home/acc-control
runuser -u acc-control -- docker --host=unix:///run/user/1000/docker.sock \
  exec -i acc-f23-runtime-broker-1 python -B \
  < /ABSOLUTE/REVIEWED/OPERATOR/infra/vps/inspect_first_recovery.py
```

Путь — точный новый защищённый operator checkout. До запуска сверяются имя и
revision существующего broker; если они изменились, требуется новая сверка.
Конструкция stdin не добавляет файл или mount в контейнер и не меняет PYTHONPATH
на неподтверждённый source. Удалённого SSH внутри скрипта нет. Эта команда здесь
не выполнялась. CLI не принимает task IDs, paths, credentials или другие args;
ошибочные аргументы отклоняются без повторения их значений.

`LOCAL_OBSERVATIONS_COMPLETE` означает только прочитанные локальные наблюдения.
В любом случае `recovery_authority_verified`, `paid_recovery_authorized`,
`deployment_authorized`, `token_issued`, provider access/token validity остаются
false. Полная проверка RecoveryExperiment.verify_parent выполняется новым
приложением при prepare/authorize и перед внешними действиями; этот reader её
не заменяет и не выдаёт grant из старого согласия.

`BLOCKED` и exit 2 сохраняют разобранные секции и fixed blockers. Истёкшие
profile evidence после паузы ожидаемы: они не обновляются диагностикой.
Исчезнувший runtime file, UNCERTAIN, неправильный fence, повреждение цепочки,
существующий контейнер или нездоровый daemon требуют отдельной сверки;
повтор старой задачи и удаление её journal не допускаются.

## После отчёта

1. Сверить локальные данные с owner checkpoint, исходным расходом и runtime.
2. Отдельно согласовать точные runtime/operator SHA, срок и build-only пакет.
3. После сборки подготовить новый plan выдачи короткого installation token;
   прежний third-token и его evidence истекли. Не повторять старые attempts.
4. Подготовить новый private recovery profile с original_task_id/grant_digest,
   свежими свидетельствами и прежним финансовым пределом; выполнить offline checks.
5. Inspect staged candidate и отдельно согласовать exact previous/candidate apply.
6. Только затем отдельная observed Telegram карточка разрешает один paid recovery.

Не нужно заново создавать GitHub App, PEM или OpenAI/source keys, если прежняя
custody действительна. Проверка отзыва или доступа провайдера требует отдельного
реального read-only запроса; этот локальный отчёт не утверждает такую проверку.

Cloud tests используют public synthetic fixtures, настоящий локальный PG,
настоящие SQLite файлы и fake Docker. Совместимость импортов дополнительно
проверяется с экспортом src установленного commit 322186d. Это не VPS acceptance.
