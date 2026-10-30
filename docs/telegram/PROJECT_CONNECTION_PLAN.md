# План подключения проекта в Telegram

Продолжение PR #62: тот же фиксированный connection plan доступен владельцу
через `/connection project-id`. `/connection` без аргумента показывает четыре
варианта, `/projects` сохраняет счётчики и команды очереди и добавляет команды
плана для каждого проекта. Полную команду с ID нужно отправлять целиком.

Для command-center, vanilla-sugar, lnauto и capital-lab выводятся ожидаемый
репозиторий, три пункта «не проверено» (repository/verification/deployment),
границы просмотра и команда очереди. Источник — прежний project_connections,
а не отдельный реестр конфигурации. Никакого процента готовности, server health,
действующего repository binding, включённого исполнения или нового AI consent.

Используются прежние private-owner normalization, connection/source/runtime
guards, F1 transaction/audit, profile-scoped inbox и delivery queue. Только
Telegram query receipt: RECEIVED → DONE и один queued reply. Это не SQL
read-only транзакция: сохраняются входящее сообщение, аудит и исходящий ответ.
Task/Approval/ExternalGrant/worker Outbox, budgets, admission и конфигурация
проектов не меняются. Команда работает при обычной остановке и не требует
исправного AI-профиля. Неизвестные IDs/лишние аргументы отклоняются до capture.

Новых callback/approval namespaces, keyboard buttons или transport методов
нет. Одно сообщение без markup/parse_mode проходит прежние character/JSON
byte limits. Дубликат update сохраняет один ответ; crash до commit продолжает
существующий pending intent. Integrity/source проверки resume_pending прежние.
UNCERTAIN send не повторяется, отзыв connection блокирует отправку до HTTP.

Новый текст не обращается к GitHub/OpenAI/VPS и не читает ключи проекта. Для
будущей реальной доставки требуется отдельное разрешение на exact source и
release; frozen recovery bf91c05/build-only package и release pairs сохранены.
На VPS эта команда здесь не устанавливалась. PR #61 остаётся отдельным первым
host-этапом после действующего доступа/разрешения.

Проверки: настоящий локальный PG и strict fake Bot API; четыре проекта и guide,
навигация help/projects, некорректные аргументы, private owner, halt, отсутствие
загрузки AI-конфигурации, authority invariance, concurrent duplicate/restart,
rollback/pending recovery, источник/целостность, audit corruption, неизвестная
отправка и отзыв connection. Существующий service-container smoke расширен
guide и четырьмя project plans, сохраняя coding task №15 и resume callback
№100/101. Fake getUpdates соблюдает запрошенный batch limit20 и выдаёт остаток
следующим poll. Это cloud mock-проверки, не реальный Telegram/iPhone/VPS acceptance.
