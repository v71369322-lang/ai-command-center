# Один локальный запуск перед восстановлением

[prepare_recovery_offline.py](../../infra/vps/prepare_recovery_offline.py) соединяет
[read-only inspection](FIRST_RECOVERY_READ_ONLY_INSPECTION.md) и
[disabled profile preparation](FIRST_RECOVERY_DISABLED_PROFILE.md) без ручного
переноса JSON и plan digest. Это cloud implementation для будущего разрешённого
локального запуска; он здесь не выполнялся на brain1.

## Область

Только control UID1000 на brain1, текущий VERIFIED deployment:

- runtime322186dc180257c618d8b159c78faa6e5bbf0b43;
- bundleac6462b47f69a3cbc967ac2c9dd62064d6b3dc7813503d34782e1dd1830d094d;
- /home/acc-control/first-experiment-github-capability-release/integration-preparation/candidate;
- существующий acc-f23-runtime-broker-1, без создания новых контейнеров;
- новый /home/acc-control/first-experiment-recovery-offline.

Приложение восстановления bf91c05 и 12 release pairs/build-only launcher из
PR #58 не меняются. Runtime update, image build, новый GitHub token и paid test
не входят в эту команду. Секреты провайдеров не читаются, не передаются через
stdin/argv или report. Git fetch/SSH/cloud-runner внутри wrapper нет; локальные Git checks проверяют pins. Operator checkout
должен быть получен и проверен отдельным разрешённым шагом.

## Последовательность

1. Проверить host/UID, clean exact operator и окно до1часа; output отсутствует,
   parent принадлежит control user и недоступен для чужой записи.
2. Взять shared lock существующего private deployment.lock без O_CREAT.
   Проверить live journal, полный bundle checksum/profile/source и protected
   original config SHA/model hash. Ключи OpenAI/GitHub не открываются.
3. Проверить control rootless daemon/cgroups и immutable broker image revision.
   Bind name→container ID: проверяются compose project/service labels, running
   state, readonly root, critical source/DB/config/Python env и bind/secret/tmpfs
   mounts. Подмена config mount или перекрытие source не допускаются.
4. Создать private0700 workspace и atomic session.json с INSPECTION_ATTEMPTED.
5. Передать только проверенный inspect_first_recovery.py через stdin в
   `docker --host=unix:///run/user/1000/docker.sock exec -i IMMUTABLE_ID python -B`.
   Timeout60сек; exit0/2 разбираются по контракту. Произвольный stdout/stderr
   не выводится и не сохраняется.
6. Проверить report предыдущим builder, удалить поля, не нужные его контракту,
   и повторно проверить сохранённый минимальный объект. Достаточно лишь blocker
   profile_evidence_missing_or_expired; иные неопределённости блокируют шаг.
7. Повторно сверить predecessor/container и окно. Сохранить private0600
   inspection.json; выполнить прежние plan→prepare автоматически с их точным pin.
8. Ещё раз сверить predecessor/container/окно и записать
   RECOVERY_OFFLINE_DRAFT_PREPARED с hashes и консервативной бюджетной оценкой.

Исходный config/journal, FAILED-задача и финансовый ledger не переписываются.
Inspector сохраняет PG read-only и SQLite mode=ro/query_only; данные providers
не используются. В draft всегда disabled mode, false live/tariff flags, пустые
свидетельства/финансовый reference и неподтверждённый баланс.

## Будущий запуск

Нужны owner-authorized local preparation, новый exact operator checkout и
существующий tools Python с тем же runtime lock. CLI принимает только operator
revision и время окончания. Они фиксируют операторский scope; наличие timestamp
само по себе не является согласием владельца или F1 grant.

```sh
# Template only. Not executed here; replace pins after explicit authorization.
cd /home/acc-control
runuser -u acc-control -- env PYTHONPATH=/ABSOLUTE/REVIEWED/OPERATOR/src \
  /home/acc-control/f30/tools/bin/python -B \
  /ABSOLUTE/REVIEWED/OPERATOR/infra/vps/prepare_recovery_offline.py \
  --operator-revision EXACT_REVIEWED_OPERATOR_SHA \
  --approved-until EXACT_APPROVED_UTC_EPOCH
```

Результат не называет draft пригодным к live-выполнению: paid/deployment/recovery
consent и token_issued всегда false. Свежие price/funding/credential/repository/
runtime/dry-run evidence, source-pinned build, короткий token и прежние
stage/inspect/exact apply/observed Telegram approvals остаются впереди.

## Неопределённость и повтор

Если workspace уже существует, команда прекращается до нового broker exec.
В существующий каталог она не дописывает и не возобновляет session. Ошибка или
смена predecessor после записи сохраняет disabled draft и BLOCKED receipt для
сверки. Ключи не перевыпускаются, контейнер не удаляется, задача не перезапускается.
Если atomic receipt не успел записаться, private intent/pending file или само
существование workspace всё равно не позволяют повторить операцию вслепую.

Timeout Docker CLI не доказывает завершение запущенного read-only Python. Это
не paid retry: новое исполнение всё равно запрещено до сверки существующего
workspace/receipt. Автоматический kill контейнера или cleanup не выполняются.

Тесты используют fake Docker и настоящие private файлы/локальную блокировку.
PG integration дополнительно проводит настоящий read-only отчёт через минимизацию
и disabled builder. Это не новый VPS/rootless/live-provider acceptance.
