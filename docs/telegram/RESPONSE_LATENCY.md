# Telegram: ожидание готовых ответов и результатов

Cloud-продолжение после [launch checkpoint](../f2-2/LAUNCH_CHECKPOINT.md).
Это runtime-доработка для будущей доставки. На текущем VPS она не применена;
application `a5d867cb734a4954926a4e77c71e6f5be217057c`, уже собранный владельцем,
и восемь именованных release targets сохраняются. Для этой доработки нужны
новые exact-source images и отдельный проверенный пакет, а не новый label старого
образа. Подготовку первого AI-эксперимента на прежнем target можно продолжать
независимо; эта доработка не становится новым обязательным условием запуска.

## Причина, найденная в коде

`poll_once` сначала восстанавливает durable inbox, затем вызывает getUpdates,
после чего обрабатывает входящие команды, собирает результаты и отправляет outbox.
Раньше даже уже сохранённый ответ ожидал long poll. Стандартный timeout10секунд
мог добавить ожидание, когда новых входящих updates нет; service также имеет
прежнюю паузу0.5секунды между успешными циклами. Результат задачи, завершившейся
во время idle poll, также ждал возврата getUpdates.

Новый update в обычном Telegram long poll может прийти сразу, до timeout.
Следовательно10секунд не были обязательной задержкой каждого сообщения.
Это найденный в control flow источник лишнего ожидания, не замер причины
конкретной задержки на VPS и не утверждение о скорости Telegram/OpenAI.

## Изменение

После recover/resume_pending bridge в существующей F1 transaction проверяет
наличие `NEW` delivery только текущего connection profile. При таком ответе
getUpdates получает timeout0. Входящие команды, включая `/stop` и отмену,
по-прежнему обрабатываются перед потенциально медленными sendMessage.
Это позволяет убрать long-poll ожидание очереди ответов, сохранив порядок controls.

Стандартное ожидание idle poll уменьшено с10 до2секунд. Явный poll_seconds по-прежнему
принимается в прежних пределах0–20. Наличие SENT/UNCERTAIN/SENDING/CANCELLED
или чужого profile не переводит idle poll в неблокирующий режим.

Пределы20updates и20deliveries за цикл, stable offset, private owner scope,
advisory leadership, source/connection checks, heartbeat, retry/backoff/429 и
durable uncertainty policy сохраняются. Ошибка getUpdates оставляет ещё не
отправленный ответ в NEW; после восстановления он доставляется один раз.
Неопределённая отправка не повторяется. Состояние NEW влияет только на timeout,
а существующие audit/body/recipient проверки определяют допустимость отправки.

## Что это означает для скорости

В idle цикле плановое ожидание опроса теперь до2секунд вместо10, плюс прежняя
пауза0.5секунды между успешными циклами. Это не гарантированный end-to-end SLA:
сеть, HTTP timeout, DB/очередь, большой пакет, backoff и сам AI добавляют время.
Уже известный NEW ответ исключает long-poll ожидание, но ожидает сетевой round trip
getUpdates и обработку входящих controls. Завершение задачи во время опроса
проверяется в том же цикле после его возврата.

Более частый idle polling увеличивает число Telegram HTTP requests; ориентир при
пустых успешных опросах — около24/мин вместо6/мин с прежней паузой. Это не новые
AI-вызовы, расходы OpenAI, grants, executor или параллельный delivery process.
Проверки не требуют настоящего Telegram bot token или доступа к VPS.

## Проверки

Регрессии используют настоящий локальный PostgreSQL и httpx.MockTransport:
nonblocking poll для durable/recovered reply, stop перед sends, общий предел
доставок при backlog, scope/state, HTTP failure, uncertain send/restart,
stop/leadership/revocation, explicit/default timeouts и terminal result,
наблюдённый во время poll. Проверяется порядок событий и протокол, без flaky
sleep-based assertion или заявления о фактическом времени на телефоне.

Локальный расширенный scope: **478 passed /4 deselected /1 существующий
Starlette-httpx warning**. Новые23 cases входят в478 и не суммируются с ним.
Ruff/OpenAPI/current-runtime-secret guard/diff check PASS; locked audit:
64 Python dependencies,0 Python/npm advisories,0 Bandit MED/HIGH и99 retained
reviewed LOW. Это working-tree evidence до commit, не final-source CI.

Старые локальные executor images не соответствуют новому source: guard не
ослабляется. Первый локальный service scope подтвердил это двумя прежними
executor_revision_mismatch; в расширенном scope четыре известных execution
cases явно deselected. Полные execution/container cases требуют свежего final-source CI;
PG/mock результаты отдельно фиксируются в Draft PR. Cloud rootful/mock tests
не подтверждают rootless VPS, реальную Telegram latency или phone acceptance.
