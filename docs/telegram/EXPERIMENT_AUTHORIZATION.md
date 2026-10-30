# Явное разрешение первого AI-теста из Telegram

Продолжение [подготовки задачи](EXPERIMENT_PREPARATION.md), поверх Draft PR #51.
После доставки нового пакета владелец сможет разрешить один фиксированный
платный тест с телефона. Эта cloud-доработка не подключает ключи, не обновляет
VPS и не вызывает провайдера.

## Путь владельца

1. `/prepare_experiment` создаёт прежнюю WAITING_APPROVAL задачу без расходов.
2. `/readiness` и `/experiment` показывают условия и задачу. Обычная остановка
   снимается отдельным существующим `/resume`; recovery остаётся блокером.
3. `/authorize_experiment` без аргументов показывает отдельную карточку: UUID,
   фиксированное упражнение `calculator.py`, модель, тестовый репозиторий,
   полный расчётный лимит двух вызовов и срок подтверждения в UTC.
4. Только кнопка **«Разрешить платный AI-тест»** в этой доставленной карточке
   выдаёт разрешение через прежний F1. Нажатие допускает реальные AI-вызовы и
   Draft PR только в показанном тестовом репозитории; merge и CRM не разрешаются.
5. `/experiment` показывает результат; `/watch_experiment` явно включает
   уведомления; `/cancel_experiment` запрашивает отмену без обещания возврата денег.

Карточка действует120секунд от receipt команды. Разрешение на запуск действует
до120секунд после подтверждения; действительность evidence и остальные условия
перепроверяются перед действиями и могут заблокировать их раньше. Продления,
автоматического повторного запуска и нового эксперимента по повторному клику нет.
Нет аргументов для выбора произвольной задачи, модели, бюджета или репозитория.
Обычные сообщения и очереди проектов по-прежнему NEEDS_PLANNING.

Требуются live-профиль с точным source/byte pin, подтверждённым тарифом и funding,
все девять прежних expiring gates и положительный полный резерв двух вызовов,
не превышающий100₽ и daily/monthly capacity. Нет готовой задачи/условий — нет
карточки разрешения. Расчётный предел не является provider-side hard cutoff;
примерные70₽/$ и наличие ключа не подтверждают payment/price evidence.

## Единственный grant path

Общая локальная `Gateway.authorize_configured` сохраняет прежний API authorize:
owner role, config hash, fixed experiment scope, F1 Store.approve, ExternalGrant,
READY и executor Outbox. API по-прежнему требует прежнюю точную typed confirmation.
Telegram добавляет альтернативное явное подтверждение через привязанную кнопку;
`/prepare_experiment`, `/resume`, просмотр и сам запрос карточки ничего не одобряют.
HTTP client/Gateway instance не создаются, credential values не читаются.

Карточка привязана к private-owner receipt, profile/source, connection digest,
UUID/version/payload hash, control epoch, бюджету, config hash и credential
references. Кнопка принимается только после сохранённого SENT и observed message
ID именно этой карточки; текст/markup сверяются с queued audit digest.
NEW/SENDING/UNCERTAIN и отсутствие delivery receipt не разрешают расходы.

Под Control lock заново сверяются receipt/card/config/ledger/task/gates/expiry.
Grant, approval, READY/outbox, consumed audit и queued acknowledgement коммитятся
одной транзакцией. Ошибка ответа до commit откатывает разрешение. Потеря local
result или Telegram acknowledgement после commit не выдаёт второй grant.
Гонки одинаковых и разных callback receipts используют тот же single-grant
constraint. Stop/recovery/source/version/price/reference changes блокируют
устаревшую карточку. Чтение статуса и повтор consumed card не восстанавливают grant.

## Доставка и проверки

Нужны новые exact-source images и отдельный named release; прежние девять targets
и уже собранный владельцем a5d867c новой команды не содержат. Runtime checkpoint
и десятый profile фиксируются следующим operator-only commit; старые pins/default
не переназначаются. Сохраняются prepare/inspect/exact approval/apply/postcheck,
private integration/readiness bindings, custody, backup, predecessor и journal.

Локально **654 PG/strict-mock tests passed /9 execution cases deselected /1 прежний
Starlette warning**. Из них64 новых authorization cases. Следующий targeted
прогон после дополнительного post-commit-loss case: **84 passed /3 execution cases
deselected**, в том числе65 новых. Наборы пересекаются и не складываются.
Проверены owner/group/message/nonce/receipt tampering, expiry, девять gates,
source/control/config/credential references, два вида concurrent callbacks,
atomic rollback и uncertain/lost replies. Fake live-shaped declarations не
являются доказательством реального тарифа, доступа, расходов или rootless VPS.
Ruff/OpenAPI/tracked-secret/diff checks PASS. Locked audit:64Python dependencies,
0Python/npm advisories,0Bandit MED/HIGH,99reviewed LOW. Final fresh-source CI и
точные source/operator SHA фиксируются в Draft PR.

Последний подтверждённый VPS остаётся d932baaf; фактическое подключение runtime,
сверка обеих GitHub token attempts, финансовых условий, deployment и первый
платный запуск остаются отдельными невыполненными действиями. Прошлое разрешение
100₽ само по себе не включает новый профиль или платный тест.
