# Первый AI-эксперимент: просмотр из Telegram

Cloud-продолжение [PR #43](https://github.com/v71369322-lang/ai-command-center/pull/43).
Команда `/experiment` без аргументов показывает существующую задачу первого
эксперимента. Её создаёт прежний API; эта команда задачу не создаёт и не запускает.
На VPS функция пока не доставлена; target пакета PR #43 её не включает.

Именованный operator profile `--release first-experiment-status` закрепляет
переход от текущего application d932baafce53c0748396abfc019cf81b931ebfec к
`1fe45031c6570bd02e4f017169462a0b29649b15`. Он требует прежний opt-in
`--first-experiment-telegram-readiness` и три private file bindings. Один новый
кандидат включает gateway profile, readiness и experiment snapshot; прежние
targets не меняются. Operator checkout закрепляется отдельно от application.
Host prepare, candidate digest/inspect и exact apply approval остаются отдельными
этапами; этот cloud profile их не выполняет.

## Что видит владелец после доставки

- UTC-время снимка, ID и состояние одной фиксированной задачи;
- режим из сохранённого разрешения: live либо явно обозначенные HTTP-моки;
- количество операций OpenAI, учтённый расход и спорный резерв по журналу шлюза;
- лимит задачи из разрешения и общий потолок первого эксперимента 100 ₽;
- подтверждённый результат и, только для валидной live-записи, сохранённую ссылку
  Draft PR выделенного синтетического репозитория.

Это записи локального журнала, не баланс OpenAI и не свежая проверка provider API
или GitHub. HTTP-моки не выдаются за реальный AI/публикацию. Если задача ещё не
создана, ответ направляет к `/readiness`. Обычные CRM-запросы не выполняются.

## Привязка и доказательства

Просмотр использует существующие owner/private-chat проверки, F1 admission lock,
audit chain и durable Telegram receipt. Принимается только request key
`owner:first-experiment-f2-2`, owner role и полный неизменный payload первого
эксперимента, совпадающий с исходным creation audit. Общий helper payload
используют API и этот reader; публичный API-контракт не меняется.

Дополнительно пересчитывается digest фактического JSON payload: одной проверки
равенства Python-словарей недостаточно, поскольку 2 и 2.0 сравниваются одинаково.
Regression test сначала воспроизвёл ошибку, затем подтвердил отказ при такой подмене.

Задача другой source revision требует сверки. Произвольный UUID/experiment tag
не расширяет область просмотра. `/tasks` и `/status UUID` сохраняют прежнюю
привязку к тестам соответствующего Telegram-подключения.

Grant проверяется по digest, owner audit anchor, source/payload/experiment/base,
режиму и budget; live-запись требует зафиксированного final confirmation.
Расходы читаются после прежней проверки ledger anchors; HTTP-клиент, Gateway
instance и FileCredentials не создаются. Общая ledger-проверка теперь static,
её алгоритм и проверки перед сетевыми операциями сохранены.

Успех требует F1 verified artifact/fence/source, coding_complete evidence anchor,
independent proof, связанных base/head/branch и корректного режима публикации.
Для live разрешён только точный URL `https://github.com/OWNER/acc-f2-synthetic-NAME/pull/NUMBER`
из сохранённого grant; произвольные URL/текст/артефакт/evidence не выводятся.
Текущее удалённое состояние PR этой командой не проверяется.

INTENT/UNCERTAIN/SETTLED означают незавершённую сверку внешнего результата.
Исправлен также прежний API status: после owner billing settlement он сохраняет
result_uncertain=true. Денежный резерв уже может быть нулевым, но повтор всё ещё
запрещён прежним Gateway guard. Список запрещающих повтор состояний общий;
финансовый reconciliation, полномочия, расходы и reservations не изменяются.

Повтор Update возвращает прежний снимок; новое `/experiment` читает свежие данные.
Потерянный send response остаётся UNCERTAIN без автоматической пересылки.
Команда доступна при обычной остановке/recovery и их не снимает. Меню содержит
команду; четыре прежние кнопки сохранены. Help больше не утверждает глобальное
«реальный AI отключён» и указывает на отдельное разрешение эксперимента.

## Проверки и границы

Локальный combined run: 151 passed / 5 deselected / 1 Starlette-httpx warning.
Это PostgreSQL + strict Bot API/provider HTTP mocks: новый reader, меню,
task-status, прежние financial/Gateway и first-experiment regression tests.
Пять container-dependent cases отложены до финального CI с exact-source images.
После последних изменений текста/лимита повторён затронутый subset:65 passed;
это пересекающиеся tests, не дополнительные65. Named staging transition:
315 passed, все шесть release profiles и прежние uncertain-result interlocks.
Существующий end-to-end dry-run дополнен чтением реального persisted результата
pipeline через Telegram: success, wrong repository и response loss.

Положительные cached live-record fixtures проверяют лишь валидацию/отображение;
это не настоящий OpenAI-вызов, grant или GitHub-публикация. Все реальные ключи
остаются на VPS. Итоговый HEAD, полные suite counts и выполненные container
checks фиксируются в отдельном Draft PR. Deployment и фактическая phone-приёмка
этим cloud-кодом не подтверждаются.
