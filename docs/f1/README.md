# F1: облачная синтетическая реализация

Статус: реализация для review, НЕ полная приёмка F1/MVP и НЕ разрешение VPS deployment.

## Источники и Git-зависимости

Ветка `feat/f1-synthetic-control-plane` основана на PR #7,
`2d34f5d13b4ef2b8d973530cd263dc2fa391e323`. PR #2–7 открыты на момент начала:
это зависимый стек, а не документация main. Исторические файлы сохранены.
PR F1 направляется в ветку PR #7 для обозримого incremental diff; перенос в main
возможен только после разрешённого владельцем разрешения зависимостей.
Никаких silent copies, merge main или настройки GitHub security.

Историческая база: R01–R51/D01–D30, H-A–H-J, особенно H-I05/06/08/10/14/16/17/20.
ТЗ F1 было подготовлено в предыдущем ответе этой сессии; отдельного файла ТЗ
в baseline PR #7 нет. Текущее сообщение владельца разрешает облачный код,
зависимости, синтетические тесты, коммиты/PR, но не SSH/VPS, реальные API и расходы.
Служебные группы F1-01–34 не являются новыми H-решениями.

## Реальные компоненты

FastAPI + PostgreSQL/SQLAlchemy + Redis, Python worker, Docker-per-run executor,
независимый verifier, React/TypeScript mobile-first web. PostgreSQL обязателен:
SQLite/in-memory fallback отсутствует. Outbox сохраняется с задачей в одной
транзакции; Redis переносит только ссылки. Единственный admission lock F1
ограничивает параллельность одним исполнителем и сериализует audit chain.

Детерминированный executor — явно **синтетический тестовый адаптер**, не настоящий
AI. Он создаёт input.json/result.md в отдельном tmpfs, отдаёт manifest;
verifier независимо вычисляет ожидаемый Markdown. Результат и SHA-256 сохраняются
в PostgreSQL до удаления контейнера. Произвольные команды/файлы не поддерживаются.

API: `/api/simulator/commands`, `/api/state`, `/api/health`, task approve/cancel/
revoke/retry, `/api/control/stop`; versioned OpenAPI доступен `/openapi.json`.
CLI simulator допускает только loopback URL. Поле sender не определяет роль.

Состояния: WAITING_APPROVAL → READY → RUNNING → SUCCEEDED;
CANCEL_REQUESTED → CANCELLED; FAILED; RECONCILING. Проверка результата выполняется
до атомарного SUCCEEDED; отдельное сохраняемое VERIFYING пока не реализовано.
Невыполненная dependency оставляет READY, но admission блокируется.

Операция = стабильный task UUID; попытка имеет возрастающий fence и lease.
Использованное подтверждение нельзя повторно потребить другой попыткой.
Повтор approved_render требует новой версии и нового согласования.
Повтор разрешается только после `verified_no_effect`, с максимумом две попытки.
Тестовые лимиты: lease 15 s, timeout 30 s, approval 1–300 s; это DERIVED профиль
облачных испытаний, не исторические значения и не гарантии VPS.

## Быстрый запуск в разрешённой облачной среде

Нужны Python 3.12, uv, Node 22/npm и Docker/Compose с доступным **локальным** daemon.
Команды запускают только собственный проект acc-f1. Не выполняйте команды тестов
на базе с реальными данными: fixture намеренно очищает таблицы F1 и останавливает
только контейнеры `acc-f1-db-1`/`acc-f1-redis-1`.

```sh
uv sync --frozen
npm ci --prefix web
npm run --prefix web build
.venv/bin/playwright install chromium
python scripts/bootstrap_secrets.py
export F1_SOURCE_REVISION="$(git rev-parse HEAD)"
docker --host=unix:///var/run/docker.sock compose up -d db redis
docker --host=unix:///var/run/docker.sock build --build-arg F1_SOURCE_REVISION -f Dockerfile.executor -t acc-f1-executor:local .
scripts/cloud_test.sh
```

Secrets bootstrap не перезаписывает существующие файлы и не печатает credentials.
Все `.runtime/` файлы исключены из Git и Docker build context. Разные admin/app DB
credentials; API не получает admin secret. Bootstrap schema выполняется явно
тестовым скриптом; API не создаёт таблицы. Это начальная schema 001, не framework
безопасных последующих миграций.

Для панели после build запустить Compose API и отдельный доверенный worker:

```sh
export F1_RUNTIME_UID="$(id -u)" F1_RUNTIME_GID="$(id -g)"
docker --host=unix:///var/run/docker.sock compose build api
docker --host=unix:///var/run/docker.sock compose up -d api
scripts/run_worker.sh
```

Секреты bind-mounted Compose должны быть читаемы только выбранным runtime UID;
проверить ownership, НЕ делать каталог секретов общедоступным. API слушает только
127.0.0.1:8000 хоста. DB/Redis не публикуются; cloud-test.sh получает адреса их
локальной Docker-сети. `compose.cloud-test.yaml` — необязательный loopback override;
на internal bridge некоторые версии Docker не активируют port publishing.

В managed cloud для сборки сохранять платформенный proxy/TLS verification:
`BUILDX_CONFIG` можно перенести в writable cache, не заменяя DOCKER_CONFIG.
Передавать CA как BuildKit secret `proxy_ca` (например, системный combined bundle);
не копировать CA или credentials в image. Обычный хост без proxy может собирать
без этого build secret. Изменение сетевой политики платформы — отдельный workflow.

Панель не публиковать в Интернет ради preview. Credential вводится защищённым
способом в локальный browser; он остаётся в памяти страницы, не localStorage.
Это синтетические identities, не реальный owner binding/MFA.

## Проверки и завершение

`ruff check src tests scripts`, `npm run --prefix web build`,
`scripts/cloud_test.sh` (реальные PG/Redis/Docker), [матрица](ACCEPTANCE.md).
JUnit остаётся `.runtime/test-results.xml`; публикуются только санитизированные
сводки. Не выгружать environment, секреты или полные Docker inspect/config.
Автономность этапа покрывает обычные исправления/тесты/коммиты/PR;
не покрывает merge, paid commitments, реальные данные, VPS и следующий этап.

Остановка cloud-контейнеров: `docker --host=unix:///var/run/docker.sock compose stop`.
Не использовать `down -v` как обычный способ остановки: он уничтожает тестовую БД.

### Дополнения проверенного профиля

Обычный stop отменяет ожидающие задачи, отзывает approvals и меняет epoch.
Owner resume требует точные epoch и checkpoint digest и не возобновляет отменённые
задачи. После restore/isolation incident обычный resume блокируется.
Outbox redelivery восстанавливается не чаще 5 s/task без роста строк на каждый poll.
Admission: максимум 100 незавершённых задач, synthetic DB size cap 64 MiB; launcher
не начинает работу при свободном workspace disk <256 MiB. Это DERIVED cloud caps,
не замена host quota/полноценного resource monitor. Worker dependency backoff bounded
2–30 s; полноценный circuit breaker остаётся OPEN.

Redis работает непривилегированно, `dir /tmp`, `save ""`, `appendonly no`:
его файловая persistence намеренно отключена. Пересоздание Redis восстанавливает
transport из PostgreSQL/Outbox и не зависит от старого RDB в `/data` образа.
