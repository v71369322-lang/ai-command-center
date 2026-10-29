# Офлайн-проверка профиля первого AI-эксперимента

Перед настоящим запуском полезно проверить operator config без credentials,
PostgreSQL или соединений с OpenAI/GitHub. `scripts/first_experiment_preflight.py`
использует существующие IntegrationConfig, FirstExperiment.report/validate_scope,
CodingRequest и nano-RUB расчёты. Приложение, Gateway, F1 permissions и orchestrator
не изменяются. Нового способа выдачи полномочий нет.

База — PR #40, `53a95559279ac3531a9f477264ee391e751aa7d2`. Target единого Telegram
обновления остаётся d932baa; эта operator-проверка не требует заново менять его
или создавать ещё один application release. VPS и реальные аккаунты не затрагиваются.

## Безопасный запуск в облаке

Закоммичен только disabled template `infra/vps/first-experiment.disabled.json`:
нет credentials/files, repository ID, свидетельств, баланса или FX upper bound;
mode disabled, live_authorized=false. Отдельный будущий реальный profile должен
оставаться в private/ignored operator workspace.

```sh
F2_INTEGRATION_CONFIG_FILE=infra/vps/first-experiment.disabled.json \
  .venv/bin/python scripts/first_experiment_preflight.py
```

Ожидается JSON **BLOCKED**, exit **2**. Это успешное подтверждение закрытого
состояния шаблона, а не ошибка подготовки. Без переменной используется тот же
существующий closed default IntegrationConfig.load(). Никакого включения mode,
создания репозитория/App, ввода ключа или оплаты команда не выполняет.

Exit **0** и `LOCAL_CHECKS_PASSED` означают только согласованность локальных
деклараций и параметров. Даже тогда `live_call_allowed`,
`final_owner_approval_verified`, `remote_state_verified`,
`provider_hard_cap_verified`, `credential_values_read` всегда false,
`external_calls` всегда0. Это результат данного инспектора; глобальное состояние
другого процесса или уже выполненные расходы из него не выводятся.

## Какие ошибки находит

- Не live mode, отсутствующий operator live flag, experiment/repository profile.
- Недостающие или просроченные девять F2.2 evidence gates.
- Отсутствующие/пустые references, один alias или один буквальный file path
  одновременно для OpenAI и GitHub. Это только metadata; существование, права,
  symlink/inode, содержимое и безопасность настоящих файлов здесь не проверяются.
- Неподтверждённый тариф, нулевой/недостаточный daily/monthly budget, неверную
  модель/context/output cap, заниженную цену и неучтённые fixed extras.
- Превышение100₽ с учётом integer rounding или недостаточную вместимость
  конфигурации для двух максимально разрешённых вызовов.

Используется существующий чистый validate_scope с условным final_confirmation=True,
чтобы оценить также следующие за consent guard финансовые проверки. Gateway/F1
authorize не вызываются, реальное согласие не создаётся и не проверяется. Поле
отчёта final_owner_approval_verified остаётся false; production auth path прежний.

Предлагаемый task budget — рассчитанный максимум двух вызовов по предоставленному
тарифу, если он положителен и не превышает100₽. Это верхний резерв, не целевой расход.
При будущем отдельно подтверждённом authorize его надо передать явно, если он
меньше API default100₽. Первый правильный ответ не требует второго AI-вызова.

`profile_hash` совпадает с существующим digest(config.model_dump()) для последующего
точного approval, но не является подписью владельца или grant. Отсутствие credentials
в hash следует прежнему config serializer; это не проверка custody/ротации ключей.

## Что намеренно остаётся отдельной реальной проверкой

1. Доступ владельца к выбранной API-модели и действительные тариф/условия оплаты.
2. GitHub App installation, минимальные права и selected numeric repository ID,
   protected exact main SHA; репозиторий и App пока не создавались этим этапом.
3. Безопасная защищённая передача credentials шлюзу, private file permissions,
   отсутствие ключей у исполнителя и процедура отзыва. Ключи в чат не присылать.
4. Текущий runtime, F1 halt/recovery, уже выданный единственный experiment grant,
   существующие расходы/спорные резервы и оставшийся room в DB ledger.
5. Успешный dry-run для выбранного source/config и точное окончательное разрешение
   владельца на один ограниченный эксперимент.

Инспектор не читает credential_files, не создаёт Gateway, HTTP client, Store,
задачу/approval/grant, не проверяет внешние API и не изменяет ledger. Он читает
только выбранный JSON config через прежний loader. Parser/read errors дают
redacted BLOCKED без paths, input values или traceback. В отчёте нет произвольных
model/repository names, evidence/credential references или file paths.

Локальные декларации о FX/наличии средств не гарантируют upstream списание в RUB.
CBR reference и внутренний резерв не заменяют подтверждённую all-in границу
с комиссиями/налогами. Предварительные100₽ не разрешают оплату; закупка credits,
подключение аккаунтов и первый paid call по-прежнему требуют отдельных решений.
Исходный [план F2.2](EXPERIMENT_PLAN.md) и runtime guards не ослаблены.

## Практические проверки

Новый offline suite: **58 passed**. Проверены все9 missing/expired gates,
disabled/mock/live metadata, budget/tariff/scope/rounding validation, separate
credential references, отсутствие Gateway/HTTP/Store/approval действий,
redaction/private paths, malformed/symlink/oversized config и настоящий CLI
на disabled defaults/template. В положительных случаях используются публичные
синтетические декларации, не настоящее model/balance/repo evidence.

Весь infrastructure suite: **338 passed**, новые58 входят в338. Отдельно16
существующих pure F2.2 validation tests passed /6 deselected /1 прежний warning.
Эти16 входят в полный Python suite и не заменяют его.

Настоящий запуск CLI с закоммиченным template дал BLOCKED, exit2,0 external calls,
credential_values_read=false. В ignored `.runtime/first-experiment-preflight/`
сохранён JSON этого закрытого прогона. Это не full coding dry-run; полный
HTTP-mock repair/verifier/publisher cycle остаётся отдельной контейнерной проверкой.
Финальный CI нового operator SHA и результат полного mock cycle фиксируются в PR.
