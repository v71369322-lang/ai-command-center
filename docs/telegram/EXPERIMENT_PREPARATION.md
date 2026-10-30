# Подготовка первого AI-теста из Telegram

Продолжение [PR #50](https://github.com/v71369322-lang/ai-command-center/pull/50).
До этой доработки единственная фиксированная AI-задача создавалась через
`POST /api/experiments/first/task`; Telegram предоставлял её просмотр, подписку
и отмену. Новая `/prepare_experiment` переносит этот подготовительный шаг в
личный чат владельца. VPS/credentials/live API этим cloud-этапом не меняются.

## Поведение после доставки

`/prepare_experiment` без аргументов создаёт ровно прежнюю задачу F2.2:
сумма положительных чисел в `calculator.py`, фиксированный Git baseline,
provider OpenAI, максимум2вызова. Новая задача имеет **WAITING_APPROVAL**.
Это определение будущего настоящего AI-теста, не запуск mock-исполнителя.
Provider при подготовке не вызывается; никакого вывода о подключённом AI нет.

API и Telegram используют общий `create_task` и один request key
`owner:first-experiment-f2-2`. Повторное сообщение, другая команда подготовки,
перезапуск или предварительное создание через API возвращают тот же UUID.
Готовая/отменённая/ошибочная/неопределённая задача не становится новым запуском.
Новая команда не создаёт Approval, ExternalGrant, ExternalAction, executor
Outbox или запись расходов. Она не снимает обычную остановку и recovery.

Просмотр: `/experiment`; условия: `/readiness`; явная подписка:
`/watch_experiment`; отмена: `/cancel_experiment`. Существующие команды `/tasks`
и `/status UUID` сохраняют прежнюю отдельную scope синтетических Telegram-тестов.
Обычный текст и выбор проекта остаются сохранёнными запросами NEEDS_PLANNING;
они не превращаются в фиксированное упражнение и не отправляются провайдеру.

Финальное разрешение расходов остаётся в прежнем first-experiment authorize
path с точными task/version/profile/budget/deadline и всеми runtime gates.
Эта команда подготовки не является новым способом paid approval. Подключение
ключей, подтверждённого тарифа, GitHub token и runtime на VPS всё ещё необходимо.

## Атомарность и границы

При получении private-owner команды существующий audit фиксирует source,
profile, intent hash, admission epoch и immutable binding уже существующей задачи
либо отсутствие задачи. Без существующей задачи halt/recovery отклоняют intake.
Существующую задачу можно только сослать даже при остановленном control.

Общий Store.create с прежним scope installer выполняет task creation, проверку
receipt, task/inbox linking, audit и постановку ответа в одной F1 transaction
под Control lock. Потеря постановки ответа откатывает новую задачу. Intent,
сохранённый до process crash, может примениться один раз в пределах120секунд;
stop/epoch/recovery/source/connection change блокируют отложенное создание.
Старый source receipt сохраняется для сверки, не получает новый source молча.

При отсутствии задачи на intake допустима только текущая WAITING_APPROVAL
задача, созданная не раньше этого intake. Это допускает безопасную гонку двух
подготовок одного fixed request, без разрешения выполнений. Если существующая
задача была закреплена на intake, другая задача под тем же ключом отвергается.
Проверяются owner, exact payload и фактический digest, исходный creation audit
и source; числовое JSON tampering вроде2→2.0 не проходит через Python equality.

Модуль не создаёт Gateway/HTTP client и не читает OpenAI/GitHub credentials или
live config. Учтённые расходы и спорные резервы существующей задачи сохраняются.
Потерянная отправка ответа остаётся UNCERTAIN без автоматической пересылки.

## Доставка

Функция и прежнее сокращение Telegram polling требуют новых exact-source images.
Существующие восемь release targets и собранный владельцем a5d867c не содержат
новую команду. Operator profile для единой доставки закрепляется отдельно после
runtime checkpoint; прежние source pairs не переназначаются. Новый профиль не
создаёт host bundle и не заменяет prepare/inspect/exact approval/apply/postcheck.
Выдача GitHub token делается после длительных prerequisites, а не до сборки.

## Проверки

Настоящий локальный PostgreSQL и строгие HTTP mocks проверяют единственный
API/Telegram UUID, конкуренцию/restart, отсутствие grants/executor outbox/provider
calls, сохранение terminal/active history и ledger, source/intent/binding tampering,
atomic rollback, expiry/epoch/recovery/connection revocation и lost reply.
Публичные mock usage/unknown reserves в tests не являются реальными расходами.
Локально **542 passed /7 deselected /1 прежний Starlette-httpx warning**:
45новых cases входят в542, не добавляются ещё раз. Семь execution cases требуют
fresh-source images и остаются обязательными в CI. Targeted new/API scope:
64passed /3 runtime cases deselected; он пересекается с расширенным scope.
Ruff/OpenAPI/current-runtime-secret guard/diff check PASS; locked audit:
64Python dependencies,0Python/npm advisories,0Bandit MED/HIGH,99reviewed LOW.
Это working-tree evidence до commit, не результат финального source CI.
Полный итог final source/image CI фиксируется в Draft PR; старые local images
не переименовываются ради source guards. VPS/rootless/phone acceptance остаются
отдельными от cloud PG/mock/container evidence.
