# Сводка готовности Commander с телефона

Облачная доработка поверх PR #38 (`f69f1fb23af9fbf0c5c5345721d8dcc3b8679b28`).
Прежний application target пакета PR #38 — `bdc8cbc`; он не включает эту новую
команду. Доставка нового application SHA требует собственного закреплённого
пакета и отдельного разрешения. Сейчас VPS и действующий бот не изменяются.

## Использование после доставки

В личном чате владельца `/readiness` возвращает один текстовый снимок:

- время UTC и source revision именно Telegram-обработчика;
- открыт ли приём новых разрешённых задач, обычная остановка или recovery;
- число исполнений в тех пяти состояниях, которые блокируют существующий F1
  resume: RUNNING, VERIFYING, CANCEL_REQUESTED, RECONCILING, SECURITY_BLOCKED;
- число запросов этого подключения в NEEDS_PLANNING;
- режим локального AI-профиля и условия первого эксперимента, если профиль
  предоставлен обработчику. В live отдельно показан операторский флаг, который
  сам не заменяет разрешение задачи.

`/help` и `/menu` содержат ссылку-команду. Прежняя клавиатура с четырьмя кнопками
сохранена. `/status UUID` по-прежнему читает отдельный синтетический тест.
Аргументы `/readiness` не принимаются. Авторизация прежняя: только привязанный
владелец в private chat, без forwarded message или sender_chat.

Это моментальный снимок. Повтор одного Update возвращает тот же durable receipt;
новое сообщение `/readiness` создаёт свежий снимок. При недоступной PostgreSQL
или повреждённом audit ответ с успешной проверкой не отправляется. Ответ после
потери HTTP response остаётся UNCERTAIN, автоматически не пересылается.

## Что именно означает AI-статус

В прежнем deployment-профиле Telegram не смонтирован конфигурационный файл шлюза и его
credentials. Поэтому по умолчанию сообщение говорит **«Состояние gateway
неизвестно»**. Отсутствие файла в этом процессе не доказывает отключение другого
сервиса. Старые bundles сохраняют это поведение.

Cloud-продолжение поверх [PR #42](https://github.com/v71369322-lang/ai-command-center/pull/42)
добавляет явный opt-in `deployment prepare --first-experiment-telegram-readiness`
вместе с тремя existing first-experiment file arguments. В manifest binding
появляется только `telegram_readiness: true`; false/строки/другие значения
отвергаются, отсутствие поля сохраняет прежний профиль. При наличии Telegram
его служба получает readonly config и обязательный SHA-256 pin. Mounts OpenAI key
и installation token остаются только у broker; сетевые права Telegram прежние.
Postcheck проверяет pin в работающем Telegram и actual readonly mount metadata.
Эта функция ещё не доставлена на VPS; прежний application target PR #42 её
не содержит и не переименовывается в новую версию.

Если оператор ранее предоставил `F2_INTEGRATION_CONFIG_FILE`, используется
существующий `IntegrationConfig.load()` и `FirstExperiment.report()` с текущим
временем PostgreSQL. Выводятся только фиксированные подписи режимов, флаг и
названия недостающих/просроченных условий. Произвольные model names, repository
names, evidence references, paths, credential references и значения не выводятся.
Ошибка чтения/валидации даёт unknown без текста исключения.

Актуальные свидетельства в локальном профиле не доказывают текущую доступность
OpenAI, GitHub, worker/watchdog, состояние баланса или окончательное разрешение.
Эти удалённые проверки сводка не выполняет. Она не открывает credential files,
не создаёт Gateway, не вызывает paid API или publisher. Обычные запросы остаются
в очереди планирования; mock coding явно обозначен. Условия и расчёт первого
эксперимента остаются в [F2.2](../f2-2/EXPERIMENT_PLAN.md).

Сводка не меняет Control, задачи, grants, approvals, Outbox или financial ledger.
Неопределённые расходы сохраняются. Синтетические единицы F1 не выдаются за RUB
или фактический баланс OpenAI. `/resume` остаётся отдельным двухшаговым действием
со всеми прежними блокировками; paid consent через эту команду получить нельзя.

## Доказательства

Mobile opt-in: локально **183 passed / 1 Starlette-httpx warning** — deployment,
config byte pin и readiness через actual PostgreSQL + strict Bot API mock.
Включены прежние regressions и 22 новых cases; пересекающиеся прогоны не суммируются.
Container smoke расширен API/Telegram config-only и отказом при изменённом pin;
его выполненный результат и полный финальный CI фиксируются в новом Draft PR.
На VPS и к платным provider API эти проверки не обращаются.

Локально **126 passed / 1 прежний Starlette-httpx warning**: новая сводка,
прежние menu/control/task-status regression tests, настоящая PostgreSQL и строгий
HTTP MockTransport. В них входят **30 новых tests**. Поднаборы не складываются.
Отдельно **210 infrastructure passed**; Ruff, OpenAPI, TypeScript/Vite и
security/dependency gates PASS (64 Python dependencies, 0 Python/npm advisories,
0 Bandit MED/HIGH, 84 reviewed LOW). Окончательные результаты полного CI финального
SHA фиксируются в PR; локальный known-secret guard не является универсальным аудитом.

Новые сценарии покрывают open/halt/recovery и пять F1 resume blockers,
connection-scoped queue count, missing/invalid/symlink/oversized profile,
disabled/mock/live profile, fresh/expired/missing experiment evidence, отсутствие
чтения ключей/утечек references, неизменность полномочий и спорного AI-резерва,
owner/group/forward/argument denial, concurrent duplicate, restart/crash rollback,
unknown delivery, revoked connection, недоступную БД и повреждённый audit.

Существующий `telegram_service_smoke.py` расширен `/readiness` через настоящий
service container, PostgreSQL и fake Bot API. Проверяется один доставленный
unknown-without-profile снимок. Coding repair, independent verification, mock PR
и подтверждённый normal resume остаются частью того же сценария. Итог полного
контейнерного прогона будет указан в CI; исходники smoke не являются доказательством
его выполнения. Реальный Telegram/VPS/iPhone acceptance этой версии не проводился.
