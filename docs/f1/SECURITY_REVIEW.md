# Критическое ревью F1: текущая облачная итерация

Отдельная последующая проверка PR #8 и исправления:
[REVIEW_PR8.md](REVIEW_PR8.md). Она выполнена в отдельной ветке, но той же
сессией; полностью независимое внешнее заключение по-прежнему не заявляется.

Это review выполняющего агента, не отдельное независимое заключение другого
reviewer. Независимый verifier результатов исполнения — отдельный механизм и
не заменяет независимое review значимого изменения H-D05/H-I10.

## Исправления

| Находка | Последствие | Исправление / проверка |
| --- | --- | --- |
| CANCEL_REQUESTED превращался в RECONCILING при expired lease | После сверки отменённая операция могла стать кандидатом owner retry | Сохраняется намерение отмены; regression test запрещает retry после reconciliation |
| compare_digest(str) не принимал не-ASCII credential | Неавторизованный запрос мог вызвать 500 | Сравнение bytes, ограничение длины; negative auth test |
| Короткий контейнер мог завершиться до inspect | Результат принимался без фактической проверки isolation metadata | Обязательный inspect перед принятием результата; fail closed/security trip |
| JSON true сравнивался с integer fence 1 | Нарушение строгого контракта manifest | Проверка точного типа int перед сравнением |
| Validation error мог повторять входные данные | Случайный секрет мог попасть в error response | Общий безопасный 422; OpenAPI обновлён; negative echo test |
| Secret fields попадали в dataclass repr | Возможная утечка при диагностике | repr=False для credentials; regression test |
| UTF-8 данные раздувались ASCII-escaping между API и executor | Валидная Unicode-команда могла превысить input limit | Ограничение байтов и компактный UTF-8 transport; real executor regression |
| Resume при ещё неизвестном исходе | Некорректное представление готовности контура | Запрет до завершения reconciliation; pending grants отзываются |
| Forecast не учитывался в отображаемом threshold | UI мог показывать 0 при budget restriction | Threshold по max(actual+reserved, forecast); regression test |
| Audit denial блокировал async event loop | Риск задержки управляющих запросов | Offload в bounded thread pool; bounded HTTP rate state |
| Worker получал owner/operator bearer secrets | Ненужные credentials у launcher | Worker не монтирует identities; API/agent boundaries сохранены |
| Recovery CLI мог наследовать удалённый Docker context | Риск случайного обращения к другому daemon | Единый local_docker и shell wrapper: Unix socket, selectors удаляются, proxy/CA/registry сохраняются; regression без сетевого обращения |
| В dev-lock использовался pytest 8.4.2 | Аудит выявил PYSEC-2026-1845 (дублированный advisory для одной уязвимости) | Обновлён pytest 9.1.1; аудит теперь охватывает runtime и dev dependency closure |

## Решения в пределах разрешения F1

- Контейнерный worker — тот же доверенный launcher с полномочиями локального
  облачного Docker daemon, а не новый административный сервис. API/executor
  socket не получают. Никакого privileged/host networking или доступа к VPS.
- Docker CLI закреплён digest; app/worker — разные build targets. Секреты
  остаются runtime mounts, в образ не копируются.
- 60 requests/min/IP и bounded LRU на 1024 источника — DERIVED профиль F1.
  Это дополнительная защита, не durable authorization и не distributed rate limit.
- Audit проверяется streaming batches, без загрузки всей цепочки в память.
- Дополнительный restore drill использует другой контейнер PostgreSQL, tmpfs,
  network=none, без портов. Local trust включён только в disposable drill;
  primary PostgreSQL settings не меняются. Это не offsite disaster recovery.

## Статический анализ: явная triage, без подавления результатов

Bandit сохраняет полный JSON. MEDIUM/HIGH, ошибки scanner и новый неразобранный
LOW rule блокируют verify_cloud.sh. Для текущих LOW rule выполнен review:

- B404/B603/B607: argv-based subprocess без shell=True; команды локального Docker,
  Git и security tools. Не исполняются команды/пути из недоверенных сообщений.
  Endpoint фиксирован Unix socket; Docker PATH внутри worker — readonly image.
- B110: отказ журналирования или недоступная PG в cleanup не создают разрешение
  и не объявляют success; исполнение останавливается, evidence удерживается.
- B105: boolean `admin_db_secret_mounted: False` — факт проверки mounts, не пароль.

Последующая итерация bounded operations добавляет в тот же scan также
`infra/vps/operations`, без расширения списка разрешённых LOW rules. Subprocess
там ограничены fixed argv Git/OpenSSL/systemd и test-only UID proof. Enrollment
проверяет Git commit/tree/blob identities и выполняет Git как unprivileged runner.
SHA-1 с usedforsecurity=False используется только как формат Git object ID;
владельческое разрешение дополнительно фиксирует SHA-256 bootstrap/catalog.
Private receipt key создаётся как acc-control; root не запускает его Python venv.
Результаты операций подписываются стандартным Ed25519, проверяются cryptography
и OpenSSL. Ключ не доступен runner, API или coding executor. Shared host/daemon
compromise не исключён этой схемой. Полномочия и resource limits описаны в
[BOUNDED_OPERATIONS_CHANNEL.md](../infrastructure/BOUNDED_OPERATIONS_CHANNEL.md).

SQL interlock строится через psycopg.sql.SQL/Literal, не через конкатенацию
неэкранированных данных. Полный набор LOW наблюдений не удаляется из отчёта.
Это triage текущего кода, а не независимое security certification.

## F34 operator helper

В scan добавлен infra/vps/stage_telegram_update.py. Его две LOW B105 относятся
к сравнению token_file с фиксированным in-container путём /run/telegram/token.
Это ссылка на защищённый binding, не значение credential. Staging вообще не
открывает token; approved apply делегирует прежний credential preflight trusted
Deployment. Оба наблюдения сохраняются в Bandit JSON. LOW allowlist не изменён,
новые MEDIUM/HIGH или неизвестные rules по-прежнему блокируют CI.

## Первый experiment deployment binding

Новый deployment_integrations проверяет config/credential custody через
O_NOFOLLOW descriptors. Значения keys при prepare/preflight не читаются;
App PEM не является installation token и превышает разрешённый size cap.
Полный byte pin дополняет прежний profile hash, исключающий credential paths:
redirect reference на другой runtime secret отклоняется ещё loader до Gateway.
Readonly config находится только в API/broker, keys и opt-in egress только в
broker. Прежний запрет произвольных mounts/env/networks остаётся для defaults.
Binding не выдаёт grants и не ослабляет budget/final confirmation guards.

В retained Bandit JSON добавились8 LOW observations: B105 — фиксированный
in-container `/run/f2/github.token`, не secret value; B404/B603/B607 нового
networkless cloud smoke — argv-only Git/local Unix Docker для exact source
и публичных disposable fixtures, без shell=True/недоверенных task inputs.
MEDIUM/HIGH отсутствуют в локальном scan. Allowlist rules не расширялись,
findings не подавлялись. Полный dependency/static scan final SHA — в CI.

Следующий mobile opt-in добавляет readonly config Telegram без credentials,
новых сетей или grants; legacy binding без флага остаётся прежним. Postcheck
проверяет actual mount/pin. В public-fixture smoke точечно отмечен B106:
`token_file='/run/telegram/token'` — fixed container selector, не значение токена.
Только этот false positive имеет локальный nosec с объяснением; список разрешённых
Bandit rules не расширяется. Остальные retained findings продолжают проверяться.

Cloud reader `/experiment` ограничен точным owner request key/payload и creation
audit, source pin, grant digest/anchor и прежним Gateway ledger digest check.
Он не создаёт Gateway/HTTP clients, не читает credentials, не выдаёт grants и
не вызывает reconciliation. PR URL выходит только после completion/verification
anchors и exact synthetic-repository URL validation. SETTLED трактуется как
неопределённый результат в status так же, как в существующем no-repeat guard;
settled money не означает полученный результат. Cached live fixtures не являются
внешним live evidence. Новый reader не добавляет network/file execution sinks.

Experiment notices требуют явный owner/private receipt с immutable intent и
fingerprint, audit ordering и профиль/source/task binding. Collector повторно
использует верифицирующий snapshot без Gateway/client construction. UTC timestamp
исключён из semantic delivery key; уже существующие SENT/UNCERTAIN/CANCELLED
delivery не переиспользуются как NEW. Unsubscribe меняет только известные NEW
notices и сохраняет начатые/неопределённые sends. Схема и финансовые/F1 grants не
меняются; rootful mocked results не означают внешние live evidence.

## Не закрывать без внешнего evidence

Host-compromise isolation, независимая custody/immutability checkpoints/backups,
key escrow, watchdog и emergency access, VPN/HTTPS/MFA и реальные VPS quotas.
Контейнеры одного Docker daemon не являются независимыми failure domains.
RPO≤15min/RTO≤4h остаются provisional. Исходные owner requirements не ослаблены.
