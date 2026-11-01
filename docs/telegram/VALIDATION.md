# Telegram text foundation — результаты проверки

Дата: 2026-10-27. Облачная среда, только синтетические данные.
Проверенный код: `36a0f8e55e7b11bc55cce30347d2f687401adb36`.
Последующий коммит документации не меняет этот код; статус его CI нужно
проверять в Checks соответствующего Draft PR.

| Проверка | Фактический результат |
| --- | --- |
| Полный `scripts/cloud_test.sh` | **300 passed**, 1 предупреждение; включает 34 Telegram-теста. |
| Целевой `tests/test_telegram_bridge.py` | **34 passed**; входит в 300, отдельно к ним не суммируется. |
| `pytest infra/vps/tests -q` | **32 passed**, отдельный набор. |
| Ruff, OpenAPI, Git whitespace, текущие runtime credentials в tracked files | PASS. Последний скан не является универсальным детектором секретов. |
| TypeScript/Vite | PASS. Браузерные тесты существующей мобильной панели также вошли в полный Python-набор. |
| pip-audit всех locked dependencies / npm audit | 64 Python dependencies, 0 Python advisories, 0 npm advisories. |
| Bandit | 0 MEDIUM/HIGH, сохранены 49 ранее разобранных LOW findings; они не объявляются отсутствующими. |
| Образы app/worker/broker/F1 executor/F2 executor | Пересобраны с source label точного проверенного SHA; pinning не отключался. |
| Зашифрованная копия → отдельный networkless PostgreSQL → interlock/audit | PASS. |
| Контейнерные API/worker, approval, verifier, closed web | PASS. |
| Перезапуск контейнеров, persistence, cancellation, новая работа | PASS. |
| SIGKILL worker → независимый watchdog → подтверждённое отсутствие runtime → точный resume | PASS в облачном тестовом профиле. |
| F2 coding: провал тестов → repair → independent replay → mock PR | PASS. |
| Runtime API/worker permissions, secret mounts, loopback binding | PASS. |
| F2.3 закрытый профиль, задача, encrypted restore, recreate/restart | PASS отдельного повторного `scripts/deployment_smoke.py` после освобождения диска. |
| Официальная документация Bot API | HTTP 200; найдены разделы Update, CallbackQuery, getUpdates, sendMessage, InlineKeyboardButton. Это не вызов настоящего бота. |

## Сквозной Telegram-тест

Fake getUpdates → синтетический `/demo` → durable inbox → F1 task → fake
sendMessage с карточкой → callback → F1 approval/Outbox → настоящий облачный
Redis → Docker executor → независимый verifier → fake sendMessage результата.
Состояние той же задачи проверено через существующий API. Повторы не создают
вторую задачу или уведомление об одном и том же результате.

Отрицательные сценарии: чужой sender/chat, группа, бот-отправитель, forward,
voice, известный runtime secret, oversize и malformed payload; подмена nonce,
message ID, версии, epoch и Git revision; просроченная/использованная карточка;
конкурентные повторы и stop; crash между созданием задачи и записью карточки;
PG failure и audit corruption; подмена тела доставки; HTTP 403/429/500 и потеря
ответа без слепой повторной отправки; recovery неопределённого delivery;
недоказанный SUCCEEDED; отсутствие Telegram-прав у runtime role; запрет live
transport и произвольного Bot API метода.

## Что пришлось исправить при проверке

1. В облачной среде оставался F2 image старого SHA и использовался неверный
   путь Chromium. Первый общий запуск: 284 passed / 11 failed. Образы
   пересобраны, задан существующий `PLAYWRIGHT_BROWSERS_PATH`; проверки
   source/image pinning не менялись.
2. Новый тест recovery ошибочно ожидал `QUEUED`, хотя контракт F1 использует
   `READY` после approval. Промежуточный запуск: 299 passed / 1 failed.
   Исправлен тест, дополнительно проверены unused approval и единственный
   durable Outbox. Итоговый полный Python-набор: 300/300.
3. Последний deployment-smoke общего `verify_cloud.sh` корректно отказал
   с `host_disk_low` из-за накопившегося VFS-кэша облачного Docker. После
   удаления 11 untagged образов трёх прежних ACC build revision и семи
   точно выбранных старых cache ID сборки ACC dependencies свободное место
   выросло до 5,4 ГБ. Сохранены исходники, действующие образы, тома БД и release
   archive. После исправления причины повторён только deployment-smoke: PASS.
   Порог свободного места не ослаблялся. Общий локальный скрипт до очистки
   завершился ошибкой; его полный успешный повтор этим документом не заявляется.

Остаётся предупреждение Starlette о deprecated httpx TestClient. Проверки
не пропускались ради зелёного результата. Логи хранятся в игнорируемом
`.runtime/telegram-*.log`; долговременное повторное доказательство — CI Draft PR.

## Границы доказательств

Bot API — только HTTP mocks. ID владельца и URL токена — публичные синтетические
фикстуры. Настоящие Telegram credentials, отправка/приём, голос, AI-планирование
и фоновой Telegram polling service не подключены/не реализованы.
Обычный текст сохраняется как `NEEDS_PLANNING`, а не исполняется как бизнес-задача.

Облачный Docker использует явный тестовый профиль. Настоящие dual-rootless
daemon, reboot/systemd и мобильный Telegram-клиент на VPS этим не проверены.
`deployment_smoke` подтверждает облачную сборку профиля, а не разрешение или
готовность production deployment. VPS, Windows и CRM в этой работе не использовались.

Из-за новых таблиц эта ветка **не совместимое F31 password-only update**:
сначала необходимы отдельно проверенные миграция, backup/restore и откат.
Полные границы и следующий этап: [TEXT_FOUNDATION.md](TEXT_FOUNDATION.md).
