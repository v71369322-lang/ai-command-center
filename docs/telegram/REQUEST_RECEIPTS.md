# Сохранённые запросы: номер и просмотр из Telegram

Продолжение PR #25, исходный SHA
`2f50fbb148eb116378fe69bcc3e3a9eb44fe0245`, в отдельной ветке
`feat/telegram-request-receipts`. Сохраняется цепочка #25 → #24 → #23 → #22 →
#21 → #20 → #17. Пакет F32 по-прежнему закреплён за a994de9, не меняется и
не получает эту доработку автоматически. VPS и внешние подключения не меняются.

## Сценарий владельца

1. После отдельного live-подключения бот получает обычный текст владельца.
2. PostgreSQL сохраняет его как `NEEDS_PLANNING`, без Task/Approval/Outbox.
3. Ответ: «Запрос №123 сохранён», `/request 123` и явное «ожидает планирования».
4. `/requests` показывает до пяти последних сохранённых запросов этого
   подключения, с сокращённым текстом (до 160 символов).
5. `/request 123` показывает полный разрешённый текст запроса и состояние.

Это приём и поиск запросов, **не AI-планирование и не запуск coding-agent**.
Слова внутри запроса остаются данными. Отправка «потрать деньги», «измени CRM»
или «дай новые права» не создаёт разрешений и не запускает команду.
Существующие `/tasks` и `/status UUID` относятся к синтетическим F1-тестам,
а `/requests` и `/request номер` — к ожидающим планирования сообщениям.
Номер запроса не является approval, ключом доступа или глобальным ID проекта.

## Нумерация, целостность и секреты

Номер — точный Bot API Update ID в пределах текущего owner/bot/mode profile,
от 0 до `2**53-1`. Это не последовательный счётчик и не task UUID. Старые
записи уже имеют такой ID; новая таблица, миграция и перенумерация не нужны.
При ConfiguredTelegramHTTP profile стабилен между source revisions: после
обновления старые сохранённые запросы доступны тому же владельцу/боту/mode.
Legacy MockTelegramHTTP сохраняет прежнюю revision-scoped семантику.

Прежде чем показать текст, bridge требует:

- существующий owner/private-chat и connection/leadership/revocation guard;
- целую audit chain и текущий profile;
- состояние NEEDS_PLANNING, capture intent и отсутствие task link;
- fingerprint текста и соответствующий исходный owner audit event
  `telegram_update_received` с profile, Update ID и intent hash;
- повторную проверку размера/типа текста, известных credentials и известных
  форматов ключей. Обнаружение не является универсальным DLP-сканером.

Повреждение текста/ссылки/fingerprint или отсутствие audit anchor блокирует
ответ. Недоступный и отсутствующий номер дают один ответ без чужого содержимого.
Нет parse_mode, HTML/Markdown-команд, tool calls или передачи в AI. Предпросмотр
нормализует пробелы; полный просмотр сохраняет исходный разрешённый текст.
Ответы ограничены существующим Telegram лимитом; raw input — до 2000 байт,
список — до пяти preview. Не отправляйте секреты и клиентские данные боту.

В отличие от первоначального receipt, просмотр создаёт дополнительную копию
текста в существующем durable TelegramDelivery и приватном чате владельца.
Новые recipients, публичные ссылки или внешние хранилища не используются.

## Повторы и восстановление

Запрос и его acknowledgement записываются с прежним admission/audit lock.
Capture и query не изменяют Task, Approval, dispatch Outbox, admission, epoch
или бюджет. Чтение доступно при halted admission, без auto resume.

Повтор Update не создаёт второй запрос/ответ. Конкурентная обработка проверяет
NEEDS_PLANNING/DONE внутри того же lock. Сбой до коммита оставляет RECEIVED;
существующий `resume_pending` проверяет source/audit intent и завершает запись
без необходимости повторной доставки Telegram. Неопределённый send остаётся
UNCERTAIN и не повторяется вслепую. Новое сообщение `/request номер` — отдельное
явное чтение. Отсутствие ответа бота не означает потерю сохранённого запроса.

Пустой/пробельный текст и пустой `/task ` теперь отклоняются, вместо создания
пустого «сохранённого запроса». Имеющиеся inbox/delivery capacity limits
(по 1000 записей) не изменены; бесконечное хранение/автоочистка не заявляются.

## Проверки

`tests/test_telegram_request_receipts.py`: реальный облачный PostgreSQL и fake
Bot API. Проверяются номер/границы, read-only authority, последние пять,
full/preview limits, чужой chat/profile, отсутствие/подмена audit anchor,
подмена текста/fingerprint/task link, повторная проверка credentials, literal
prompt injection, concurrency/restart, crash/recovery, uncertain send и
отказ DB/audit/revocation. `test_telegram_service.py` отдельно проверяет
стабильность номера после source upgrade через ConfiguredTelegramHTTP.

`scripts/telegram_service_smoke.py` в полном CI запускает настоящий ограниченный
контейнер сервиса с actual PG и mock HTTP: capture, numbered receipt,
`/tasks`, `/status`, `/requests`, `/request`; два polling cycles, без повторных
ответов, socket или опубликованных портов. Остальные старые smoke сохраняются.

Команды локально: `scripts/cloud_test.sh tests/test_telegram_request_receipts.py`;
полный контейнерный CI: `scripts/verify_cloud.sh` на чистом SHA с такими же
source-pinned образами. Итоговые числа и CI URL — в отдельном Draft PR.

Реальный Telegram, iPhone-клиент, VPS rootless/systemd, постоянный deployment
channel, AI-провайдер и производственные проекты этой работой не проверяются
и не подключаются. Пароли/токены в чат, Git и AI prompt не передаются.
