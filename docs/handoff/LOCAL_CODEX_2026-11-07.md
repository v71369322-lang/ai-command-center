# AI Command Center — handoff в локальный Codex

Дата handoff: **7 ноября 2026, Москва**.

Этот документ — точка входа для нового локального Codex-чата. Сначала прочитать
`AGENTS.md`, затем этот файл и `docs/STATUS.md`. Старые сообщения чата и старые
SHA не заменяют фактическую проверку GitHub/VPS.

## Зачем работа переносится локально

Владелец оставляет Windows-компьютер онлайн и работает с телефона. Локальный
Codex может самостоятельно держать SSH-сессию, читать журналы и выполнять
согласованные серверные операции. Облачный чат требовал ручного копирования
PowerShell-команд, что стало главным источником задержек и ошибок ввода.

Локальный агент должен выполнять рутинные read-only проверки, edits/tests/PR и
уже явно разрешённые ограниченные операции самостоятельно. Merge, новый VPS
apply, paid AI, публикация и расширение прав по-прежнему следуют `AGENTS.md`.

## Репозиторий и GitHub

- Repository: `v71369322-lang/ai-command-center`
- Canonical branch: `main`
- Точный `main` после PR #85:
  `f5ff8b2757b1b759b08a173fdac9d3e51f84d227`
- PR #84 (`Telegram inbox control`) merged:
  `8bdb20be710e28b1d376fdaaf4b23f221a8b4141`
- PR #85 (`Telegram planning admission`) merged:
  `f5ff8b2757b1b759b08a173fdac9d3e51f84d227`
- Ruleset `main` ID `26360230`: PR обязателен, required check `synthetic`,
  approvals `0`, запрет deletion/non-fast-forward. Старое legacy branch
  protection rule удалено.
- GitHub App installation: `176497504`.
- Project connection `command-center` зарегистрировано как `VERIFIED_DISABLED`;
  execution, paid AI, merge и deployment не включены этим соединением.

Перед изменениями выполнить `git fetch origin`, проверить `origin/main` и
создать отдельную ветку от фактического `main`. Не продолжать старую удалённую
feature-ветку из cloud workspace.

## Что уже работает в production Telegram

До последней неопределённой попытки обновления был подтверждён release:

- revision `8bdb20be710e28b1d376fdaaf4b23f221a8b4141`
- bundle `16c86a771355ef42e293a6f399bf713af01bc8214f8561efb0a8b33ab322ea8c`
- directory `/home/acc-control/telegram-inbox-control-candidate`
- deployment/activation `VERIFIED`
- Telegram `live_connected=true`, status `polling`
- watchdog ready, broker ping true, OOM false
- Telegram и watchdog memory 256 MiB

Live acceptance для PR #84 выполнен:

- неизвестная `/revieew 123` не сохраняется как запрос;
- `/archive_request 131179132` успешно архивировал запрос;
- `/archive_request 131179160` успешно архивировал запрос;
- восстановление доступно через `/restore_request NUMBER`.

Task admission оставался остановленным; paid calls `0`.

## Последняя операция VPS: СОСТОЯНИЕ НЕОПРЕДЕЛЕНО

Для PR #85 был успешно подготовлен candidate:

- target revision `f5ff8b2757b1b759b08a173fdac9d3e51f84d227`
- predecessor bundle
  `16c86a771355ef42e293a6f399bf713af01bc8214f8561efb0a8b33ab322ea8c`
- candidate bundle
  `e7330efad3d1333205a0816c7153ed7fdd1c9b4fc55c888535bf6aea6f8a9918`
- source `/home/acc-control/telegram-planning-admission-release/source`
- candidate `/home/acc-control/telegram-planning-admission-candidate`
- preparation state `STAGED_NOT_ACTIVATED`
- external AI profile disabled, paid calls `0`.

Затем был запущен exact apply unit:

`acc-telegram-planning-admission-apply.service`

Он завершился exit-code и разорвал SSH. Полный диагностический снимок не был
сохранён в чат. Из последней read-only проверки подтверждено только:

`{"watchdog_ready": true}`

**Запрещено повторять apply.** Возможны оба состояния: старый release остался
активным либо новые контейнеры уже запущены, а postcheck/journal остался в
`INTENT` / `DEPLOYMENT_ATTEMPTED`. В предыдущем обновлении встречался именно
второй сценарий с кратковременным postcheck failure.

## Первый обязательный шаг локального агента

Подключиться к VPS read-only и собрать один фактический снимок:

- systemd status/journal указанного unit;
- `/home/acc-control/f30/state/deployment.json`;
- candidate `activation.json` и `preparation.json`;
- container image IDs/revision/running/exit/OOM/memory;
- broker ping из API container;
- Telegram health;
- watchdog ledger readiness.

VPS:

- host `176.12.75.135`
- user `root`
- Windows key `C:\Users\Zver\.ssh\ai-command-center`
- рабочая короткая команда владельца из PowerShell:
  `ssh -i .ssh/ai-command-center root@176.12.75.135`

Не выводить секреты, environment values, Telegram token, DB passwords или
private key. Не менять runtime в первой сессии.

Если фактически target containers уже работают, deployment journal `INTENT`,
activation `DEPLOYMENT_ATTEMPTED`, а все exact postchecks проходят, использовать
существующие штатные инструменты только после проверки их preconditions:

- `infra/vps/reconcile_deployment_intent.py`
- `infra/vps/reconcile_runtime_memory_activation.py`

Reconciliation не должна перезапускать runtime или менять binding. Если evidence
не совпадает — остановиться с точным блокером, без retry/rollback наугад.

## Возможность PR #85

Команда `/plan_prepare NUMBER`:

- создаёт одну idempotent F1 task типа `saved_request_plan`;
- закрепляет request text/fingerprint, project assignment, control epoch и
  source revision;
- оставляет task в `WAITING_APPROVAL`;
- не создаёт provider client, credential read, ExternalGrant/ExternalAction,
  расход или execution;
- при normal stop/recovery задачу не создаёт;
- изолирована по Telegram profile.

После успешного reconcile/deployment проверить feature на новом тестовом
запросе. Для создания planning task normal stop должен быть отдельно снят через
существующий `/resume` flow. Старые отменённые задачи не возобновлять.

## Следующая разработка

После стабилизации PR #85:

1. Trusted live planning gateway для Responses API на существующих F1 authority,
   ExternalGrant и financial ledger.
2. Operator-provided model/tariff/budget evidence; ничего не угадывать.
3. Отдельное Telegram-подтверждение exact request, model, maximum reservation и
   expiry до каждого provider call.
4. Один вызов на exact context; uncertain outcome без автоматического retry.
5. Ответ сохраняется только как advisory draft `/plan NUMBER`; execution false.
6. Затем отдельный этап plan acceptance -> isolated coding -> verifier -> Draft
   PR. Merge/deployment остаются отдельными owner approvals.

OpenAI balance `$8`, сообщённый 31 октября, устарел и не является разрешением
расхода или текущим billing evidence.

## Границы других проектов

`Vanilla & Sugar`, `LNAuto` и `Capital Lab` пока не подключать автоматически.
Сначала закончить безопасную цепочку на `command-center`. Доступы, CRM data,
календарь, Яндекс/Google files, реальные финансовые или торговые операции не
следуют из этого handoff.
