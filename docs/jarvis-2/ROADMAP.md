# Jarvis 2.0 — единый маршрут к ежедневному использованию

Источник — утверждённая владельцем концепция Jarvis2.0 и приоритеты её этапов.
Текущее место: **этап2 из6, минимальная рабочая версия ещё не завершена**.
Количество PR не является прогрессом продукта. Каждый отчёт должен называть
общий этап, проверенный пользовательский результат и оставшийся следующий результат.

| Этап | Состояние | Что считается завершением |
| --- | --- | --- |
| 1. Аудит и упрощение | Основной переход выполнен | AI-разработчик выключен, данные и backup сохранены; необратимая очистка остаётся отдельной согласуемой операцией |
| 2. Минимальная рабочая версия | **В работе сейчас** | Быстрый Telegram, проверенный голос → сохранённая запись/задача, проекты/Inbox/заметки/вложения, календарь с созданием событий по поручению, работающие напоминания |
| 3. Интеллектуальный помощник | Следом | Управляемая память и Decision Log, брифинги, приоритеты, нагрузка, ограниченная проактивность и конструктивный стиль |
| 4. Развитие и наставничество | Позже | Цели/привычки, библиотека, прогресс, цитаты, наставники с источниками и образовательные сценарии |
| 5. Бизнес-интеграции | Позже | Ограниченное чтение Capital Lab и двух CRM с источником, периодом и актуальностью; финансовые записи/операции не разрешаются |
| 6. Стратегическая аналитика | После достоверной базы | Обзоры целей/ресурсов/решений и персонализированное наставничество на доступных данных |

## Текущая ближайшая последовательность внутри этапа2

1. **Первое ускорение установлено и проверено25 ноября.**
   На3bcf8e4 реальный /help UI→SENT6.02s, Calendar14.09s с работающим voice;
   новая фраза «что у меня завтра в календаре?» распознана правильно.
   Старый Calendar53.31s был с другой очередью, поэтому это не строгий A/B.
   Первая существенная оптимизация подтверждена; постоянную скорость ещё наблюдаем.
2. **Первый голос → распознавание → подтверждение → сохранённый запрос проверен25 ноября.**
   Реальное5s сообщение: расшифровка через10.08s после приёма; подтверждение
   владельца создало NEEDS_PLANNING без задачи/AI/Calendar write. Дальше —
   качество пунктуации, имён, дат, адресов и длинной речи, удобное исправление.
   Один пример не закрывает голосовую приёмку: [критерии](VOICE_QUALITY.md).
   PR116 установлен; второй настоящий voice прошёл Reply-правку, отказ старой
   карточке, однократное сохранение и просмотр правильного текста в Telegram.
   Исходный ASR ошибся — улучшение качества распознавания этим не подтверждается.
3. **Закончить календарь для повседневных поручений.**
   PR119 установлен26 ноября: реальная Telegram-кнопка создала одну встречу
   в основном Calendar; signed readback, Google UI, reminder20min, agenda и
   повтор до/после restart без дублей проверены. Изменение/удаление существующих
   событий не подключено. Широкое понимание фраз, пересечения и полная голосовая
   приёмка остаются ограничениями; точные данные карточки проверяет владелец.
4. **Закрыть задачи/Inbox/проекты/напоминания в одном понятном сценарии.**
   Переиспользовать существующие записи и инструменты; проверить сроки, исправления,
   статусы и напоминания. Отличать сохранённую идею от задачи и завершённого действия.
5. **Общая приёмка минимальной версии.**
   Короткое поручение без обязательных специальных команд, понятное подтверждение,
   сохранность после штатного перезапуска, отсутствие дублей, понятный отказ при
   сбое Google/сети, восстановление из проверенной копии. Отдельно измерить задержку.

После завершения этой последовательности этап2 закрывается пользовательской
приёмкой. До этого не переключаться параллельно на наставников, CRM и стратегические
обзоры. Ранее написанный компонент не переписывать без доказанной необходимости.

## Границы

Платные AI-вызовы по-прежнему выключены. Разработка подключения/конфигурации
сама по себе не разрешает расходы или передачу данных модели. Интеллектуальное
понимание длинных смешанных поручений не выдавать за готовое на основании
распознавания речи или нескольких правил фраз. На модель и конкретные лимиты
понадобится отдельное разрешение перед реальными вызовами.

Новый deployment — точный пакет, актуальные проверки, backup и действующее
разрешение; merge не следует автоматически из разработки. Google write scope,
необратимая очистка и внешние бизнес-доступы — отдельные действия. Исторические
разрешения на другие версии не считать бессрочными.

## 26 November personal planner live checkpoint

PR121 including PR120 installed with exact owner approval. Task/idea separation,
undated deferred plans, explicit project correction/recall, completion, persistence
after the same poller restart, combined existing Google agenda and one actual
11:18Moscow Telegram reminder all verified. Pre/post encrypted backups independently
verified on PC. [Evidence and limits](../handoff/JARVIS_PERSONAL_PLANNER_LIVE_2026-11-26.md).
Next acceptance is a real fresh owner phone voice -> reviewed personal task;
then close the remaining Stage2 attachment/failure/speed checks before Stage3.
No paid AI, recurring reports, new calendar scopes, merge or other projects.

26 November08:30UTC: fresh actual8s owner phone voice -> owner-confirmed personal
task in confectionery with no deadline verified in UI and joined DB evidence.
Proposal10.96s after intake; personal creation0.204s after acceptance. The next
check is remaining Stage2 attachment/failure/speed acceptance, not repeating this
successful path. Broader ASR quality and mixed-message understanding remain open.

## 26 November attachment release live checkpoint

PR123/source0259ce4 including PR122 installed after exact approval. Actual public
Telegram document/photo -> reference + own copy -> project/status -> poller/voice
restart -> trusted byte-integrity read PASS. No OCR/AI content interpretation or
file-resend UI is delivered. Google agenda after restart18s, photo status12s.
Both journals VERIFIED; paid calls0. Pre/post PC encrypted custody checked and
post backup isolated restore audit VERIFIED. Initial/intermittent poller exits
repaired; cause unestablished, uptime observation remains necessary. Authenticated
owner web Inbox live200 not run, API scope checks passed in final CI.
[Exact evidence and recovery](../handoff/JARVIS_ATTACHMENT_RELEASE_2026-11-26.md).
Next useful bounded result is convenient owner retrieval of a stored file, then
combined long phone voice / corrections / tasks / reminders / calendar acceptance.
Do not declare Stage2 complete or start Stage3 from the attachment check alone.

26 November: next attachment retrieval slice implemented in Draft PR124/sourcec25e2d3.
Final CI45815091382 PASS: main2909/1skip/1warning, infra1014, speech44.
Get-file button/plain numbered request uses existing owner delivery, checked DB
copy, exact connection and no-retry uncertainty; no new service or paid AI.
Not installed. Next step is separately approved exact release with actual two
public fixture retrievals and restart/no-duplicate checks, followed by combined
Stage2 voice/correction/task/reminder/calendar acceptance. Stage3 not started.
