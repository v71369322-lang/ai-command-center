# Закрытый F1 backend планирования на HTTP-mock

Продолжение [Draft PR #54](DRAFT_STORAGE_AND_TELEGRAM.md). Реализован внутренний
цикл подготовки обычного плана через прежние F1 approval и financial ledger.
Это **закрытый HTTP-mock backend**, не включение живого AI или нового runtime.

## Цикл

1. Owner `planning_task.create_task` создаёт WAITING_APPROVAL задачу
   `saved_request_plan` для точного PlanningContext. Один request key на
   request/context; terminal/unknown задача не становится новой попыткой.
   Payload и актуальность intake/project/source/control проверяются самим
   Store.create под Control lock, включая прямой внутренний вызов Store.
2. Отдельный `PlanningGateway.authorize` требует owner, точный config hash,
   bounded budget/seconds и literal
   `AUTHORIZE_SAVED_REQUEST_PLANNING_HTTP_MOCK`. Confirmation первого платного
   calculator-теста здесь недействителен. Профиль проверяется и до ожидания lock,
   и внутри approval transaction; локальная validated copy не меняется молча.
3. Прежний Store.approve создаёт Approval/READY/Outbox атомарно с узким
   ExternalGrant. Грант связывает task/version/payload/source, request/context,
   model/profile/budget, единственный mock reference и максимум один вызов.
   Другой creation key не разрешает второй grant для того же exact context.
4. В изолированных тестах прежний F1 claim потребляет одноразовое approval и
   устанавливает lease/fence. Gateway повторяет общие F1 проверки и добавляет
   planning scope/current-context checks. Общий coding gateway отвергает этот
   grant; planning gateway отвергает coding grant. Coding status не выдаёт
   planning permission за разрешение `calculator.py`.
5. Принимается только точный Responses document из PR #53: без tools/query,
   другой модели, tier, endpoint или publisher. Один immutable key `planning/v1`.
   Shared gateway делает durable INTENT/reservation до I/O, затем подтверждает
   bounded usage и записывает response/ledger anchor. Используются те же
   ExternalAction, daily/monthly/pending limits и no-repeat states, а не второй
   счётчик расходов. Это mock-значения, не баланс или расходы OpenAI.
6. Строгая проверка/сохранение draft, binding audit и Store.finish коммитятся
   одной F1 transaction. Scope installer повторяет authority/current context и
   привязку ответа к COMPLETE external action. Ошибка finalization откатывает
   draft и task result вместе. Уже учтённый HTTP-mock расход сохраняется;
   повтор при действующем grant использует cached COMPLETE response без HTTP.

Завершение этой F1 operation означает только structurally accepted mock proposal.
Artifact явно содержит `mode:http_mock` и `business_execution:false`; original
saved request остаётся NEEDS_PLANNING, новые бизнес-задачи не создаются. Draft
по-прежнему owner_supplied_unverified/provider_evidence_verified:false. Контракт
не доказывает качество плана, реальный источник, тесты кода или работу CRM.

## Общие interlocks

Общие F1 role/Approval/lease/fence/source/audit/grant проверки вынесены в
`Gateway.f1_authority`; purpose-specific authority и request contract сужают их.
Coding и planning имеют разные purpose/контракты при одном пути прав и учёта.
Существующие generic simulator/coding API не принимают planning creation;
generic task approve возвращает external_scope_approval_required. Новый API или
Telegram generate/approve command не добавлен. Прямое F1 approval без
planning ExternalGrant не позволяет provider I/O.

Tariff для settlement копируется из admitted profile до I/O. Смена конфигурации
во время ответа блокирует продолжение, но не переоценивает уже совершённый вызов
по новому тарифу. Это относится и к прежнему coding gateway; actual/reservation
не откатываются вместе с rejected result. `cost=1` в F1 payload — прежняя
синтетическая единица, не рубль и не fee провайдера.

INTENT/UNCERTAIN/SETTLED сохраняют неопределённость и запрет повтора. Context или
project version change не позволяет обойти unresolved результат того же request.
Explicit owner billing attestation закрывает только деньги, не восстанавливает
ответ и не выдаёт новый grant. Revocation/stop/profile/lease changes проверяются
до I/O и до принятия результата; отмена во время HTTP не отменяет учтённый расход.

## Почему это ещё не живое подключение

PlanningConfig по умолчанию disabled. Тип вообще не содержит live mode или
credential-file fields, env loader отсутствует. Constructor требует enabled
HTTP-mock и настоящий `httpx.MockTransport`. Credentials — только фиксированный
PUBLIC mock marker, реальные OpenAI/GitHub файлы не читаются. Значения fixture
tariff/budget_evidence не являются актуальными тарифами, funding или consent.
Внутренние helpers предназначены для изолированного test PG, не для создания
mock expenses в живом ledger владельца.

**Production RuntimeBroker отклоняет новый kind до claim/launch**. Generic Runner
отклоняет чужой kind перед Docker и не объявляет HTTP-операцию verified_no_effect
через synthetic reconcile. Defensive watchdog classification сохраняет unknown
reservation даже при подтверждённом отсутствии контейнера. Это не доказательство
нового rootless planning runtime: такой runtime здесь не реализован.

Для live нужны отдельные проверенные account/model/pricing/funding/data-sharing
conditions, scoped approval UI/API, защищённый profile/key binding, поддержка
broker/watchdog/runtime и новый exact-source deployment package. Нельзя включить
их сменой одного enabled flag или первым calculator grant. First-experiment
bundle, все10 прежних release pins, mounts/egress/schema остаются прежними.
На VPS ничего не доставлено, actual last-confirmed source d932baaf; keys/token
reconciliation и первый отдельно разрешённый real pilot остаются pending.

## Проверки

Первый expanded local scope: **335PG/strict-mock passed /5 source execution cases
deselected /1 прежний Starlette warning**, включая49 новых cases тогдашней версии.
Последующий core/control scope: **67passed /1 прежний warning**, включая52 новых
gateway cases и15 прежних F1 tests. Наборы пересекаются и не складываются.
Финальный expanded local scope после добавления всех guards: **338passed /5
source execution cases deselected /1 прежний warning**, включая все52 новых cases.
Старый дополнительный boolean-fence executor test локально остановился на
executor_revision_mismatch; guard сохранён, тест остаётся обязательным в fresh CI.

Проверены full F1 waiting/approve/claim/mock HTTP/draft/finish, owner roles,
profile/hash/consent/budget, purpose isolation, generic API denial, payload
forgery, concurrency, unknown results, cached response recovery, atomic finalization,
revocation during I/O, admitted-tariff settlement, shared global ledger room,
context-change/no-repeat и watchdog reservation preservation. Runtime dispatch
blocking проверен до engine access. Нет реальных API/provider/rootless/VPS/phone
acceptance. Final source/CI фиксируются в отдельном Draft PR.
