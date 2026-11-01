# Отключённый профиль восстановления без ручного редактирования JSON

Владелец разрешил продолжить облачную часть плана, пока не за компьютером.
[prepare_first_recovery_profile.py](../../infra/vps/prepare_first_recovery_profile.py)
автоматизирует только подготовку нового private draft. Скрипт не обращается
к VPS сам и здесь не создавал реальный host-профиль.

Runtime остаётся `bf91c05c754ad41e7f89223ec8d05c02c9007de1`; build-only launcher и
12 release pairs не меняются. Этот helper выполняется локально существующим
operator Python с PYTHONPATH проверенного нового operator/src, не внутри старого
broker. Установленный broker322186d по-прежнему используется для
[read-only inspection](FIRST_RECOVERY_READ_ONLY_INSPECTION.md).

## Входы и проверка

Входы — исходный защищённый first profile и JSON, полученный из текущего
inspect_first_recovery.py. API-ключ, PEM или installation token не нужны.
Данные остаются локально у control UID; stdout не содержит paths, references,
модельный исходник или credential values.

Скрипт принимает отчёт не старше 300 секунд, с фиксированным task ID, read-only
scope и нулевыми provider calls/authority flags. Нужны закрытый FAILED parent,
совпадающие профиль/grant hashes, один завершённый AI-вызов без резерва,
проверенные audit/action ledger, DONE runtime без pending runs и отсутствие
контейнера при здоровом rootless daemon. Единственный допускаемый blocker —
profile_evidence_missing_or_expired: это ожидаемо после паузы и не переносится
в положительные свидетельства нового профиля.

Исходный profile должен иметь прежние repo/id/model/context/output/credential
references. Ключи не читаются; допускаются только /run/f2/openai.key и
/run/f2/github.token под прежними раздельными aliases. В новой задаче максимум
один вызов и без исправления. Старый actual плюс новый консервативный reserve
не превышают исходный grant budget, общий потолок100₽ и отдельный cap новой
попытки34.7868₽. Проверяется также консервативная оценка по историческим payment
terms; тариф или лимит не повышается автоматически.

## Что создаётся

Новый profile.disabled.json сохраняет модель/repo, исторические числовые payment
terms/тариф и отдельные parent task/grant digest. При этом всегда:

- mode=disabled, live_authorized=false, budget_evidence="";
- tariff.confirmed=false, его reference заменён явной исторической пометкой;
- first_experiment.evidence={}, existing_credit_usd=null;
- id=f2.2-recovery-1, max_calls=1, max_repairs=0 через прежний тип RecoveryExperiment.

Нет нового token, task, Approval, ExternalGrant, финансового резервирования или
подключения AI. Простой flip операторских flags не заменяет свежие девять
свидетельств и separate paid consent. Исходный FAILED/grant/ledger не меняются.
Общий deployment configurator отклоняет такой disabled profile до подготовки
binding. Полная eligibility/authority проверяется приложением позднее по PG;
локальный отчёт и этот draft её не заменяют.

## plan и prepare

Реальное выполнение на brain1 требует отдельно разрешённого локального шага.
Нужен чистый exact operator checkout, непривилегированный control user,
существующие 0700 parents и 0600 protected input files. Output — новый
отсутствующий каталог вне Git/source, active state и прежних release directories.

```sh
# Templates only, not executed here. Select exact reviewed operator commit.
cd /home/acc-control
runuser -u acc-control -- env PYTHONPATH=/ABSOLUTE/REVIEWED/OPERATOR/src \
  /home/acc-control/f30/tools/bin/python -B \
  /ABSOLUTE/REVIEWED/OPERATOR/infra/vps/prepare_first_recovery_profile.py plan \
  --operator-revision EXACT_REVIEWED_OPERATOR_SHA \
  --source-profile /PRIVATE/ORIGINAL/config.json \
  --inspection-file /PRIVATE/INSPECTION/report.json \
  --output-directory /PRIVATE/NEW/recovery-draft
```

plan только читает и возвращает hashes, бюджетную оценку и plan_digest;
files_created=false. prepare с теми же аргументами и `--plan-digest` из отчёта
создаёт private0700 каталог и два файла0600: profile.disabled.json и preparation.json.
Этот digest — pin входов и пути, а не разрешение владельца. Отдельное подтверждение
каждой команды не добавляется: plan/prepare входят в один разрешённый локальный
этап подготовки файлов.

Между plan/prepare повторно проверяются clean operator, защищённые входы, их
raw hashes и свежесть отчёта. Даже изменение только whitespace меняет pin.
Вывод не перезаписывается. При частичной ошибке результат сохраняется для
сверки; CLI указывает неизвестность files_created и возможный partial output,
не удаляет файлы и не повторяет запись.

## Дальнейшие реальные шаги

После draft отдельно сверяются новые model/price/payment/funding/runtime/
credential/repository/dry-run evidence. Короткий installation token получают
после сборки и по новому reviewed plan. Старые attempts не возобновляются,
PEM/OpenAI/source keys не пересоздаются без необходимости.

Преобразование отключённого draft в live candidate — следующий отдельный шаг
с проверяемым свежим evidence и pin. Затем прежние stage/inspect/exact apply
interlocks и новая observed Telegram paid recovery card. Этот helper не умеет
promote/activate, применять deployment или снимать stop.

Проверки используют публичные fixtures и локальный PG. Есть сквозной сценарий
«завершённый synthetic source-contract failure в PG → read-only report → disabled
draft»; это не новый live AI-тест и не VPS acceptance.
