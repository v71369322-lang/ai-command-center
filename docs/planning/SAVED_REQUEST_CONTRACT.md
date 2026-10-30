# Обычный запрос → предложение AI-плана: офлайн-контракт

Продолжение [Draft PR #52](https://github.com/v71369322-lang/ai-command-center/pull/52).
Первый платный эксперимент остаётся фиксированным `calculator.py`; его grant
не позволяет планировать обычные запросы или обращаться к CRM. Этот компонент
готовит отдельную границу будущего планировщика без provider I/O и новых прав.

## Что реализовано

`request_planning.context(store, role, request_id)` читает один сохранённый
NEEDS_PLANNING запрос через прежние `captured_text`, project history и F1 audit
проверки под Control lock. Только owner. Снимок включает immutable text/fingerprint,
request ID/profile, project ID и assignment version, intake/current source revision,
control epoch/halt/recovery. Контекст не включает другие запросы, содержимое repo,
CRM, credentials, endpoints или предположение, что доступ к проекту предоставлен.
Старый intake source может пережить upgrade, но новый снимок закрепляет текущий
source. Это позволяет планировать сохранённый текст после обновления, не выдавая
его за новый Telegram intake или прежнее execution approval.

`request_document(snapshot, model, context_tokens=…, max_output_tokens=…)` только
создаёт документ Responses API: developer rules отдельно, весь request context
как untrusted user data, `store:false`, default tier и strict JSON schema.
Нет tools, previous response/session, API client, endpoint вызова или токена.
Модель выбирается доверенным будущим caller, а не текстом запроса. Числа limits
проверяются структурно; размер JSON не является token estimate, тарифом или
доказательством достаточного funding. Эта функция не разрешает передачу данных
провайдеру или расходование денег.

`decode_response` проверяет completed/model/response ID, целочисленный usage и
его сумму/границы. Разрешены reasoning items, которые игнорируются и не возвращаются
как план, и ровно одно завершённое assistant message с одним output_text.
Tool calls, refusal, incomplete/multiple outputs, duplicate JSON keys, extra fields,
избыточный размер и другой context digest отклоняются фиксированной ошибкой,
без эха provider body/Pydantic input. Сериализованный response object≤64KiB,
text plan≤16KiB; ограничение raw HTTP body остаётся обязанностью будущего caller.

Схема предложения: summary; от1до8 шагов, у каждого от1до3 наблюдаемых acceptance
criteria; до5 вопросов. Все строки непустые и≤300символов. Наличие вопросов
согласовано с disposition needs_clarification/ready_for_review. Для unassigned
проекта вопросы обязательны; модель не может присвоить проект или добавить
fields budget/commands/execution_authorized. Это структурная проверка, не
доказательство правильности, безопасности или качества естественного языка.
Текст шага, даже содержащий shell/URL/инструкции, остаётся данными и не исполняется.

`review_response` повторно читает текущий PG context и сверяет binding перед
возвратом предложения. Изменение текста/project version/source/control делает
прежний ответ устаревшим. Повтор/restart остаётся read-only. Известные loaded
credentials и прежние key patterns проверяются перед экспортом текста и во всех
текстовых полях предложения; это общий screen с project inbox, не универсальный
secret detector. Provider credential files и integration config не читаются.

Результат всегда `execution_authorized:false`, `task_created:false`, `stored:false`,
`provider_evidence_verified:false`. Response ID/model/usage прошли только проверку
формата; они не подтверждают происхождение от OpenAI, списание или billing evidence.
Ничего не записывается в task/inbox/audit/approval/outbox/financial ledger.
Ready_for_review означает предложение к рассмотрению, не разрешение разработки.
Fresh context/review доступны и при halt/recovery, сохраняя запрет исполнения.

## Подключение остаётся следующим отдельным шагом

Это библиотечный компонент. Новых API routes, Telegram-команд, меню, schema,
scheduler, grants, credentials, network или deployment профилей нет. Текущий
Telegram по-прежнему честно сообщает, что обычное AI-планирование не подключено;
NEEDS_PLANNING не меняется. Все десять release pins, включая runtime2822320 из
PR #52, сохранены; новый код нельзя объявлять включённым в прежний pinned target.

Будущий trusted caller должен отдельно связать актуальный context с F1 budget/
provider/data-sharing scope, проверить модель/тариф/input bound и реальные gates,
выполнить ограниченный по времени/размеру HTTP через прежнюю durable gateway/ledger архитектуру и
проверить provenance результата. Первый experiment grant для этого неприменим.
Unknown outcome не разрешает повторный вызов. Сохранение/показ предложения,
его рассмотрение и последующая подготовка ограниченной задачи потребуют явной
реализации с существующими F1 interlocks; модель не назначает себе полномочия.

Перед home SSH остаётся прежний порядок: read-only reconciliation deployment и
обеих token attempts, financial evidence, integration binding, exact candidate
approval/apply/postcheck и один отдельно разрешённый fixed experiment. Эта работа
не меняет и не повторяет host setup. На VPS последний подтверждённый source d932baaf.

## Проверки

Локально198PG/strict-mock passed /1 прежний Starlette warning:61 новых contract
cases и существующие request/project inbox/routing/picker/queue проверки.
Проверены отсутствие provider client/config/credential reads, отсутствие writes/
grants/tasks, stale snapshots, restart, подмена audit/intake, source upgrade,
secret rotation, response/tool/schema/usage tampering и сохранение injections
как неисполняемых данных. После добавления явного provider-evidence flag targeted
scope **61passed /1 прежний warning** перепроверен; наборы пересекаются и не складываются. Final source/CI —
в отдельном Draft PR. Нет настоящих AI responses, paid calls, VPS/rootless/phone
или CRM acceptance; валидный публичный fixture не подтверждает live provider.
