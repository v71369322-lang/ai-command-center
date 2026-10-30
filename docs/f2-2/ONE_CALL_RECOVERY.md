# Отдельный однократный восстановительный тест

Владелец 30 октября 2026 разрешил разработку отдельного восстановления после
[известной ошибки контракта первого ответа](SOURCE_SCHEMA_FAILURE_2026-10-30.md).
Это разрешение на cloud-код, проверки и обозримую подготовку; не новый paid
consent, host build/update, token issuance или право переоткрыть старую задачу.

## Узкая область

Новый фиксированный ID `f2.2-recovery-1` и отдельный стабильный request key
создают только одну новую задачу WAITING_APPROVAL. Исходная FAILED-задача,
её использованное разрешение, действия, audit и расходы сохраняются.
Максимум один новый модельный вызов, без исправлений/автоматических повторов.
Модель, baseline, calculator.py, независимый verifier и только Draft PR прежние.
JSON Schema уже ограничен двумя исполнимыми исходниками из PR #57; произвольные
варианты кода не добавляются в allowlist.

Максимальный новый резерв — **34.7868₽** (`34786800000`nano-RUB). При подтверждённой
границе 112.5 ₽/$ это один вызов по прежнему консервативному тарифу. Отдельно
проверяется `старый фактический расход + новый резерв ≤ старый согласованный
лимит ≤ 100₽`. Общие daily/monthly ledger guards и спорные резервы сохраняются.
С observed расходом 0.047840625 ₽ суммарная верхняя оценка 34.834640625 ₽;
это расчётный предел, не фактический расход и не provider-enforced отсечка.

## Историческое основание, не перенос полномочий

RecoveryExperiment — отдельный строгий профиль с original_task_id и
original_grant_digest. Он сохраняет прежнюю сериализацию FirstExperiment и
не выдаёт authority из одних только локальных деклараций. Проверка основания
выполняется под прежним F1 PG lock при prepare, при новом authorize и перед
каждым внешним действием, включая проверки после I/O.

Обязательны owner task с исходным фиксированным request key/payload, FAILED/
external_coding_blocked, одна попытка, нулевой synthetic reserve, iteration 1 и
отсутствие sandbox/verifier/publication результата. Старые creation/grant/failure/
execution_stopped events должны быть в целой audit chain и совпадать с source,
payload, fence и digest. Текущий source должен отличаться от исходного.

ExternalAction ledger проверяется по прежним anchors: ровно один COMPLETE
OpenAI ai/1 с POST, нулевой резерв; остальные разрешены лишь как завершённые
бесплатные GitHub/Git discovery GET. INTENT/UNCERTAIN/SETTLED, второй paid call,
publisher write, подмена ledger или другая ошибка не допускают восстановления.
Сохранённый ответ должен повторно дать именно synthetic_language_scope_violation.
Он разбирается как данные и не выполняется/не переносится в новую задачу.
Новая задача получает собственные F1 Approval/ExternalGrant/source/profile hash;
старые grants не меняются и не используются как новое согласие.

Прежний запрет второго first-pilot grant действует. У восстановления свой такой
же одноразовый grant в каждом режиме. Защита первой задачи не снимается, третьей
автоматической попытки нет. Зафиксированный parent proof входит в новый grant;
изменение исторического основания блокирует продолжение до I/O.

## Telegram и API

`/prepare_recovery`, `/recovery`, `/authorize_recovery`, `/cancel_recovery`,
`/watch_recovery`, `/unwatch_recovery` используют прежние receipt/outbox/F1
helpers с отдельным фиксированным namespace. Это не второй механизм authority.
Старые команды и их receipts/watch остаются в исходном namespace. Callback rx:
нельзя подставить вместо fx: и наоборот; message/profile/source/epoch/version/
payload/config/reference/120sec/observed-SENT/once guards сохраняются.

Карточка явно показывает исходную и новую задачи, старый расход, один вызов,
новый резерв и суммарный предел. Запрос карточки ничего не разрешает. Только
отдельный private-owner click «Разрешить платный восстановительный тест»
создаёт новый узкий F1 grant. Просмотр/отмена не требуют исправного AI-профиля;
уведомления включаются отдельно, не наследуются от первой задачи и не повторяют
неопределённые отправки.

REST: POST /api/experiments/recovery/task и
POST /api/experiments/recovery/{task_id}/authorize. Последний требует отдельный
typed confirmation AUTHORIZE_ONE_PAID_RECOVERY, текущие version/profile_hash и
явный бюджет ≤34.7868₽. Старый first confirmation не подходит. GET
/api/experiments/first описывает текущий закреплённый pilot profile и выбирает
задачу по его ID; не смешивает recovery-профиль с состоянием старой задачи.

## Доставка и оставшиеся реальные проверки

Config имеет собственный SHA/profile hash и manifest marker recovery с точным
ID. Marker обязан совпасть с RecoveryExperiment в защищённом файле. Ключи и
egress по-прежнему только у broker, readonly config — API/Telegram. Не возникает
новых mounts/networks/roles/dependencies, SQL-миграции или публичного admin URL.

Для доставки нужен отдельный named transition от подтверждённого runtime
`322186dc180257c618d8b159c78faa6e5bbf0b43` / bundle
`ac6462b47f69a3cbc967ac2c9dd62064d6b3dc7813503d34782e1dd1830d094d`.
Новый named transition `first-experiment-recovery` закрепляет runtime
`bf91c05c754ad41e7f89223ec8d05c02c9007de1` и сохраняет все прежние 11 пар.
Он требует уже настроенный first profile без recovery marker у предшественника
и точный recovery marker/readiness у нового профиля. Повторный recovery→recovery
не является допустимым переходом. models.py/admin.py идентичны установленной
322186d, проверка migration hash в прежнем stage/apply сохраняется.
Operator SHA и финальный fresh-source CI фиксируются в Draft PR. Не менять старый
config/token на месте и не подменять labels уже построенных образов.

Перед реальным apply/click повторно проверить owner deployment/parent digest,
ledger anchors, актуальные funding/tariff/model/credential gates и runtime.
Особенно подтвердить DONE исходного runtime record, отсутствие его контейнера и
здоровье rootless daemon. Не очищать/прятать UNCERTAIN в SQLite или PG ради допуска.
Сохранённый third-token и его evidence истекли 30 октября в 11:23:25 UTC и 11:18:25 UTC;
нужны новая reviewed однократная выдача и свежий профиль после сборки. PEM и
OpenAI/source keys заново не создаются при действительной прежней custody.

Cloud mock/контейнерные проверки не являются новым VPS/rootless/live acceptance.
До separate exact owner decisions ни rollout, ни paid recovery не выполняются.

## Подготовленный build-only пакет

[build_first_recovery.sh](../../infra/vps/build_first_recovery.sh) запускается
локально на brain1 как acc-control UID 1000 только после нового согласия на
точные source/operator SHA и срок до 2 часов. Перед запуском оператор получает
проверенную точную копию operator commit; main/latest не используются.
Переменные ACC_OPERATOR_REVISION и ACC_BUILD_APPROVED_UNTIL задаются этим
конкретным разрешением. Unit WorkingDirectory — защищённый operator checkout
или /home/acc-control; скрипт затем сам переходит в новый source.

Скрипт сверяет VERIFIED predecessor/revision/bundle/directory, чистый operator,
новую отсутствующую workspace, source-key custody, 25 GiB свободного места и
оба rootless daemon. Создаёт отдельную private workspace
/home/acc-control/first-experiment-recovery-release и build.log, получает только
закреплённый application commit по существующему source SSH key с обязательной
проверкой known_hosts. Сборка использует прежний build_release.sh и передаёт
исполнительные образы второму daemon. Уже существующую workspace не повторяет.

Пакет не меняет binding/config, не создаёт token, не применяет deployment и не
вызывает OpenAI. Итоговый marker: FIRST_EXPERIMENT_RECOVERY_IMAGES_BUILT_NOT_DEPLOYED.
Образы привязаны к runtime bf91c05; последующие operator-only commits не требуют
пересборки приложения. Новый private recovery config, offline inspection,
точные candidate/previous digests и apply approval — следующий этап после
успешного build. Не запускать прежний stage от d932baa или mobile candidate.
