# Сохранение и просмотр черновиков плана

Продолжение [контракта PR #53](SAVED_REQUEST_CONTRACT.md). Это отдельный шаг к
обычным задачам из Telegram, без подключения AI, платных вызовов и исполнения.

## Сохранение

`request_plan_store.save` — внутренний owner-only импорт уже имеющегося ответа.
Внешнего import API, команды генерации, scheduler и клиента OpenAI нет. Метод
вызывает общий locked review из PR #53: immutable intake/project/source/control
binding и строгий response contract повторно проверяются внутри F1 transaction.
Прежний публичный read-only `review_response` сохраняет свой результат и semantics.

Записывается один `saved_request_plan_draft` в существующий append-only audit:
нормализованный план, context digest, request/project/version/source, structural
model/response/usage metadata. Исходный request text и raw provider envelope,
reasoning, дополнительные response fields не копируются. Происхождение всегда
`owner_supplied_unverified`; provider evidence и execution authorization — false.
Это не подтверждение реального AI-ответа, списания, качества плана или выполненных
работ. Нет Task/Approval/ExternalGrant/ExternalAction/executor Outbox и смены
NEEDS_PLANNING; проект остаётся метаданными, без repo/CRM доступа.

Identity включает request/context/response ID/origin; сам response ID не считается
криптографическим доказательством. Exact retry возвращает прежнюю квитанцию;
другой документ под той же identity — conflict. Каждый новый ответ получает
следующий номер черновика данного запроса под прежним Control lock. Конкурентные
сохранения не переиспользуют номер. Source и document hash фиксируются сервером.
Trusted scope installer позволяет атомарно добавить будущую квитанцию/ответ;
ошибка до commit откатывает всё, потеря local result после commit не дублирует запись.
Hook не предоставляется модели или публичному API; provider I/O внутри него нет.

Всего≤100 записей, сохраняемый document каждой≤32768bytes canonical JSON. Это жёсткий первоначальный
лимит, не бесконечное хранилище. Автоматического удаления, очистки audit или
перезаписи старых записей нет. Plans сохраняются в приватной PG/audit и её backup
с теми же правами/retention. Известные loaded credentials/key patterns проверяются
во всех текстовых полях и metadata перед записью и чтением; screen не универсален.
OpenAI/GitHub credential files и integration config не открываются. NUL и
непредставимый UTF-8 текст отвергаются до ORM write, фиксированной ошибкой без
включения model body; корректный JSON сам по себе не гарантирует PG text compatibility.

## Просмотр после будущей доставки версии

- `/plan номер` — первая страница последнего черновика.
- `/plan номер версия страница` — конкретный черновик; команда «Далее» закрепляет
  оба числа, чтобы новое предложение не подменило следующую страницу старого.
- `/plan` — справка. `/request` и `/coding_plan` сохраняют прежние значения.

Reader доступен только private owner текущего Telegram profile. Он проверяет
audit chain и семантику документов: exact schema/flags/hash/source, номера версий,
response/usage bounds и context binding. При смене проекта/source/control либо
другом изменении context новый просмотр возвращает STALE и не показывает старое
содержимое. Неизвестная версия не подменяется последней. Нет плана — честное
сообщение, что черновик не сохранён и обычное AI-планирование ещё не подключено.
Ни один просмотр не вызывает генерацию, refresh, resume или выдачу grants.

Current текст повторно проверяется с актуальными known credentials, включая
transport screen. Страницы помечены «черновик», источник AI-ответа не подтверждён;
это предложение, не разрешение на действия. Summary, шаги/критерии и вопросы
показываются полностью, в plain text, без HTML/кнопок запуска. За одну команду
ставится ровно один ответ в прежний Telegram delivery outbox. Body≤8192JSONbytes,
text≤4096chars с учётом обычных notices; всего≤50страниц. Нет автоматической
рассылки всех страниц. Natural-language инструкции/shell/URL остаются данными,
структурная проверка не доказывает их безопасность или фактическую готовность.

Duplicate Telegram update возвращает сохранённый snapshot ответа; он может
описывать уже прошедшее состояние. Новый update даёт свежую проверку. Ранее
отправленное сообщение Telegram не удаляется и не становится новым разрешением.
Lost send остаётся UNCERTAIN без повторной отправки. Halt/recovery не снимаются;
сохранение свежего owner-supplied черновика при остановке не разрешает его исполнение.

## Границы текущего этапа

Миграции/schema, grants, финансовый ledger, меню-кнопки и десять прежних release
targets не меняются. Новый reader требует нового exact-source package; его нет
ни в фактическом VPS d932baaf, ни в прежнем pinned target2822320. Команду нельзя
объявлять установленной по cloud CI. Отдельный пакет обычного AI-планировщика
будет закрепляться после реализации его подключения; старые pins не retargetятся.

Источник наполнения остаётся отдельной будущей работой: нужен разрешённый
provider/data-sharing/financial scope и durable gateway/ledger с настоящим
provenance. Grant фиксированного первого эксперимента не разрешает обычные
запросы. До подключения черновики могут появиться только через внутренний
доверенный owner import; публичные тестовые fixtures не являются живым AI.
Выбор/утверждение плана и подготовка исполняемой задачи здесь не реализованы.

## Проверки

Локально **314PG/strict-mock passed /1 прежний Starlette warning**, включая
**56новых cases** (34storage/22Telegram) и прежний planning/request/project/
readiness/control scope. Проверены concurrent versions/dedup, lost result,
atomic rollback, stale contexts, typed flags/source/hash/version tampering,
capacity/size, credential rotation, private owner/profile и полная bounded
Unicode pagination с привязкой версии. Configured Bot API transport проверен
через строгий mock; реальные API/VPS/rootless/phone не использованы.
После отдельной проверки PG text compatibility: **119targeted passed /1 прежний
warning**, включая58новых cases (36storage/22Telegram) и61 прежний contract case.
Это последующий пересекающийся прогон, не добавка к314.
Общие Telegram/service/menu/health проверки: **129passed /3execution cases deselected
/1 прежний warning**. Три source/image execution cases остаются обязательными в
итоговом fresh-source CI. Ruff/OpenAPI/tracked-secret/diff checks PASS; locked
audit:64Python dependencies,0Python/npm advisories,0Bandit MED/HIGH,99reviewed LOW.
Итоговый HEAD/CI сохраняется в отдельном Draft PR; пересекающиеся наборы не складываются.
