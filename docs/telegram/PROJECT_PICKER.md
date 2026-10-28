# Выбор проекта кнопкой в Telegram

Продолжение PR #34 (главное меню). Это подготовка следующего cloud release;
в действующий F32-бот на VPS она автоматически не попадает.

## Для владельца после обновления

1. Отправить обычный текст запроса.
2. В ответе «Запрос сохранён» нажать AI Commander, «Ваниль и Сахар», LNAuto
   или Capital Lab. «Не распределён» снимает назначение.
3. Получить подтверждение выбора. Запрос остаётся `NEEDS_PLANNING`;
   разработка, доступ к репозиторию и расходы не запускаются.

На `/request номер` появляются свежие кнопки с текущей версией назначения.
Если назначение уже поменялось в панели или другом сообщении, прежний клик
не перезаписывает его. Бот сообщает «карточка устарела» и даёт команду открытия
исходного запроса. Сохраняются прежние `/assign` и HTTP API.

Карточка относится к одному конкретному запросу. Выбор не становится скрытым
проектом по умолчанию для будущих сообщений. Главная reply-клавиатура из PR #34
сохраняется; новые пять inline-кнопок расположены под самим сообщением.
Новых имён/проектов/grants не вводится; название CryptoLab этим не сопоставляется.

## Достоверность и полномочия

Используется прежний `project_inbox.classify`, F1 transaction/admission/audit lock,
profile scope, owner/private-chat/secret checks и optimistic assignment version.
Нет новой таблицы, миграции, dependency, execution approval или финансового scope.
Номер, версия и project ID в callback — метаданные, не credential и не grant.

Для каждой карточки в том же transaction записывается audit anchor
`telegram_project_picker_issued`: profile, request ID/fingerprint, версия,
delivery ID/body hash и source revision. Перед изменением и внутри classifier
проверяются этот anchor, queued body hash, delivery state `SENT`, наблюдённый
message ID и точная разметка карточки. Generic queued/observed message без
issue anchor, чужой profile, другая карточка или старая source revision
не подтверждают выбор. Хранилище не считается защищённым от trusted root.

Transport допускает только точные пять строк кнопок из server project registry,
с одинаковыми номером/версией и без дополнительных полей. Callback ограничен
1–64 байтами по [официальному Bot API](https://core.telegram.org/bots/api#inlinekeyboardbutton),
проверенному 28.10.2026; leading zeros, неизвестные ID и лишние инструкции
отклоняются. Прежние inline-подтверждения `tg:` и readonly-меню не расширяют scope.

Потеря ответа при отправке карточки оставляет `UNCERTAIN`: она не считается
подтверждённо опубликованной. Если назначение уже committed, а потерян только
ответ-подтверждение, повтор Update возвращает прежний результат без нового
назначения или автоматической пересылки. Receipt карточки и issue anchor
фиксируются атомарно; crash при назначении откатывает assignment и его receipt.
`resume_pending` использует прежний operation ID.

Кнопка не является подтверждением запуска, поэтому не заменяет execution TTL,
budget, lease/fencing и verifier. Устаревшая версия/смена source запрещают старую
карточку; halt не мешает изменению метаданных и не снимается выбором проекта.
Отзыв connection/leadership и повреждение audit не превращаются в успешный ответ.

Полный текст `/request` не обрезается ради кнопок. Если вместе они превышают
прежние 8192 байта escaped JSON, короткая карточка с кнопками ставится отдельной
durable delivery в той же транзакции. Лимиты transport не увеличиваются.

## Проверки и ограничения

Source/test checkpoint: `bbd4d08092a214ada2fd284b4905101b2085d18b`.
Локально **203 targeted passed / 1 прежний Starlette-httpx warning**, включая
34 новых теста с настоящей PostgreSQL и strict HTTP mocks: все проекты/clear,
web-version conflict/fresh card, concurrent replay, crash/restart, неверный
sender/chat/profile/message/request/project/version, source change, revocation,
secret rotation, audit corruption, неизвестная публикация, потеря assignment
reply, callback ACK, большой readback и неизменность execution authority.
Предыдущие 25/31/34/132/161 — подмножества этого набора, не суммируются.

Отдельно **105 infrastructure passed**; Ruff/OpenAPI/TypeScript/Vite PASS.
Executor действительно собран из checkpoint SHA, label проверен; pinning не
ослаблялся. Test helper теперь различает picker и execution approval вместо
предположения, что любая inline-кнопка подтверждает Task.

Service-container smoke расширен: fake Bot API сначала наблюдает отправку
карточки, затем возвращает callback выбора LNAuto; проверяются ACK, три карточки
с версиями 0/0/1 и прежние menu/coding repair/replay/mock-PR assertions.
Полный suite/container proof финального HEAD и CI фиксируются в Draft PR.

Physical Telegram/iPhone rendering не проверено. Windows/VPS/CRM/production,
реальные Bot/AI API и credentials, paid resources, public preview, deploy и merge
не использовались. F33 reconciliation и отдельное обновление VPS остаются впереди.
