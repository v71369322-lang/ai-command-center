# Google Calendar и двойные напоминания

## Пользовательский результат

Владелец отправляет в личный Telegram текст или голосовое сообщение. Commander
показывает короткий черновик: название, начало, окончание, часовой пояс и время
Telegram-напоминания. Только отдельное подтверждение владельца разрешает создать
событие в выделенном календаре **AI Commander**. То же подтверждённое локальное
событие становится источником независимого Telegram-напоминания.

Короткое название видно в календаре телефона. Подробности хранятся в описании
события и раскрываются по нажатию. MVP не приглашает участников и не рассылает
почту, поэтому случайный разбор текста не может уведомить третьих лиц.

## Безопасный поток

1. `/calendar ...` создаёт только локальный черновик. Обычная заявка проекта не
   переосмысливается как календарь.
2. Голос сначала преобразуется в текст отдельным ограниченным компонентом. В
   карточке видны и расшифровка, и разобранные дата/время; сырой голос не создаёт
   событие автоматически.
3. Кнопка «Добавить» фиксирует `CONFIRMED_LOCAL`. Это ещё не внешний вызов.
4. Calendar outbox с фиксированным request hash создаётся только при действующей
   привязке Google и отдельном разрешённом переходе.
5. Publisher использует OAuth-токен только внутри доверенного интеграционного
   сервиса. Telegram, AI-парсер и исполнитель токен не получают.
6. Ответ Google сохраняет `event.id`, `etag` и request hash. Неизвестный результат
   сначала сверяется, а не повторяется вслепую.
7. Telegram-напоминание использует существующую durable delivery, quiet hours и
   состояния `pending/confirmed/uncertain/stalled` центра внимания.

## Google binding

- OAuth 2.0 Authorization Code + PKCE;
- минимальный scope `https://www.googleapis.com/auth/calendar.events`;
- отдельный календарь `AI Commander`, а не полный доступ к основному календарю;
- refresh token хранится зашифрованно и не попадает в Git, audit, prompt или
  контейнер исполнителя;
- отключение binding запрещает новые публикации, но не удаляет события;
- изменение/удаление события требует отдельного подтверждения владельца.

## Реализованный первый слой

`calendar_drafts.py` даёт bounded owner-only журнал локальных черновиков:

- строгие IANA timezone и offset-aware start/end;
- продолжительность до 24 часов, короткий title и bounded note;
- idempotent create/confirm/cancel;
- append-only audit и проверка всей календарной истории;
- `CONFIRMED_LOCAL` явно не означает синхронизацию;
- ни task, ни provider outbox, ни API-вызов не создаются.

## Следующие срезы

Реализован Telegram-срез `/calendar`: временный детерминированный формат создаёт
карточку, а наблюдённые owner-кнопки подтверждают или отменяют ровно один draft.
Перезапуск и повтор update не создают копий; forged/uncertain card не принимается.

Подтверждённый локальный draft теперь ставит одно независимое Telegram-напоминание
через существующий durable delivery. Повторный collector не дублирует сообщение.

Реализован ограниченный русский формат с `сегодня`/`завтра`, минутами или часами,
временем напоминания и названием. Относительная дата вычисляется по серверным
часам в IANA timezone владельца. Невозможное или неоднозначное локальное время
не угадывается и требует нового уточнённого сообщения.

1. Trusted downloader/transcription worker поверх готового voice intake/readback contract.
2. Реальная OAuth-привязка выделенного Google Calendar при участии владельца.
3. Защищённая custody refresh token и deployment publisher worker.
4. Синтетическая приёмка, затем один реальный event без участников.

Офлайн-контракт Google Insert уже фиксирует минимальное событие без участников и
`sendUpdates=none`, private draft/document binding и отдельный bounded lookup для
read-before-retry. Ответ принимается только при точном совпадении idempotency
binding, title, start/end и `confirmed`; live HTTP transport этим слоем запрещён.

Durable sync state также реализован в append-only audit. Binding содержит только
calendar ID, version и fingerprint credential — само credential value не читается
и не сохраняется. `PREPARED` фиксирует exact request hash; неопределённый ответ
переходит в `UNKNOWN`, запрещает повтор и выдаёт только bounded reconciliation
lookup. Точное событие переводит его в `SYNCED`; подмена title/time/private binding
отклоняется без изменения состояния.

Voice intake также подготовлен: только owner voice с явной подписью `/calendar`,
до 120 секунд и 5 MiB в разрешённом audio MIME сохраняется как pending metadata.
Текущий слой не вызывает Telegram `getFile`, не скачивает audio и не создаёт
event. Контракт расшифровки связывает ответ с SHA-256 аудио, требует русский
bounded text и всегда возвращает `confirmed=false`/`event_created=false`, чтобы
владелец сначала увидел readback и календарную карточку.

OAuth Authorization Code + PKCE contract теперь фиксирует exact `calendar.events`
scope, offline consent, state/verifier fingerprints и token exchange без client
secret. Token response возвращает наружу только fingerprints; custody raw refresh
token остаётся обязанностью доверенного deployment layer.

Publisher orchestration также готов: он реконструирует только exact `PREPARED`
request, успешный ответ проверяет до `SYNCED`, transport timeout сохраняет как
`UNKNOWN`, а определённый HTTP rejection — как terminal `FAILED` с bounded code.
Provider response body и credential values в audit не записываются.

Google Calendar — параллельный канал и не является prerequisite подключения
первого project adapter к Telegram.
