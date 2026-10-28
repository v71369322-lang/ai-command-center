# Облачная проверка LNAuto и блокера Ванили — 28.10.2026

Отдельная проверка существующих GitHub-источников после metadata handoff PR #32.
Исходники проектов не изменялись, новые бизнес-модули не разрабатывались.
Windows, VPS, CRM-серверы, реальные интеграции и клиентские данные не использовались.
Отчёт сохраняется в Command Center; в репозитории проектов ничего не публиковалось.

## Результат

| Проект | Проверенная точка | Результат текущего запуска |
| --- | --- | --- |
| LNAuto | main, `a339242387cd5729f252613d6a3d17cbafe00007` | PASS ограниченного cloud baseline: locked install, backend/реальная PG, frontend build и браузерные проверки |
| Ваниль и Сахар | [Draft PR #1](https://github.com/v71369322-lang/Vanilla-Sugar-CRM/pull/1), `6b0ca0d4d03d26aec4d6e7511b30e42ff63b8df8` | BLOCKED preflight: Prisma checksum HTTP 403; полный C2 setup/runtime не запускался |
| Capital Lab | Не входил в этот запуск | Новых проверок нет; прежний metadata snapshot не является PASS |

Наборы разных проектов, повторные и пересекающиеся проверки не складываются.
GitHub Actions этих проектов не запускались. Их прежнее отсутствие runs на
снимках SHA не подменяется ручными проверками ниже.

## LNAuto: что действительно выполнено

Источник: [exact GitHub commit](https://github.com/v71369322-lang/LNAuto/commit/a339242387cd5729f252613d6a3d17cbafe00007).
Проверены актуальные refs и отсутствие открытых PR; использован clean detached
checkout main без переноса старой .git/.env/данных Windows. Прочитаны инструкции,
контекст, технические решения, текущий статус и тесты. После проверки **все 91
tracked file совпадают с исходными Git blob IDs**, `git status --porcelain` пуст.
Lock-файлы, версии, код и проверки не патчились.

Среда: managed cloud, Debian 13.6 x86_64; Python 3.12.14, Node 24.19.0,
Corepack/pnpm 11.25.0, Playwright 1.62.1 / Linux Chromium 151.0.7922.34.

| Проверка | Фактический результат |
| --- | --- |
| Python exact locks | Установка requirements-dev.lock с requirements.lock через `uv pip install --no-deps`; отдельный venv; `pip check` PASS |
| Backend suite | **13 passed**, без skips/warnings; `RUN_POSTGRES_TESTS=1`, настоящая PostgreSQL 18.6 |
| Миграции/DB | Baseline upgrade, повтор upgrade, downgrade, отказ при неверной версии; commit/rollback; затем явный upgrade head PASS |
| Frontend frozen install | pnpm install --frozen-lockfile PASS, исходный lock не изменился |
| TypeScript | pnpm typecheck PASS |
| Frontend unit tests | **28 passed**, четыре test files |
| Frontend production build | pnpm build PASS; Vite 8.3.5 |
| API + DB | Настоящий Uvicorn app factory: /api/v1/health/ready HTTP 200 после миграции |
| Браузер | **10 passed**, Linux Chromium; исходный Playwright suite против Vite dev + настоящего API/PG |

Браузерные проверки: 360/390/430/768/1440 px, отсутствие горизонтального
переполнения, controls ≥44×44, прямые маршруты/история/нижнее меню, Tab/Shift+Tab,
Escape/возврат фокуса, длинная форма/вложенное подтверждение, уменьшение viewport,
manifest/MIME/размеры иконок и отсутствие service worker/Cache Storage.
Форма `/ui` не отправляет записи API; рабочие страницы явно остаются заглушками.

Нефатальные сообщения frontend инструментов: рекомендация Vitest о повторном
создании jsdom; предупреждение Node о NO_COLOR/FORCE_COLOR. Они не скрывались
и не выдавались за ошибки продукта или физическую проверку iPhone.

### Изоляция и завершение

Для PG создана только новая `lnauto_cloud_test`: отдельные network/container
с уникальными именами, internal network, без опубликованных DB-портов, uid 999,
read-only root, cap-drop ALL, no-new-privileges, tmpfs, 256 MiB / 0.75 CPU /
128 pids. Использованы новые случайные synthetic credentials, сохранённые только
в приватном временном файле; после удаления БД этот файл удалён. Существующие
DB/volumes не использовались. Роль/имя БД не взяты из production.

Официальный image: `postgres:18.6-bookworm`; digest
`postgres@sha256:5c4783a8cc3f0074912164f94dfa1be4e043438f0f707cf968d7af9a0d31a2c8`.
Версия бинарного PostgreSQL проверена отдельно. Native API и Vite слушали только
127.0.0.1:8000 и 127.0.0.1:5173 внутри облачного workspace. Public preview,
tunnels и подключение реального телефона не настраивались.

После запуска принадлежащие проверке процессы, container и network удалены;
наши loopback listeners закрыты. Проверены отсутствие container/network и
чистота source tree. Данные существующих Docker volumes не удалялись.

Первичная подготовка frontend встретила ENOSPC: локальный cloud disk заполнился
после загрузки PostgreSQL image. Освобождены только остановленные read-only
ACC test containers, неиспользуемые старые промежуточные test images и build cache
старше часа. Release-архивы, исходники, DB volumes и VPS не менялись. После
устранения причины frozen install повторён и все перечисленные проверки прошли.

### Команды для повторения в новой разрешённой cloud-задаче

Использовать exact SHA и toolchain выше. Зависимости устанавливать по исходным
locks; secrets передавать через private environment, не печатать config/URL.
Для `POSTGRES_*` нужна только собственная новая disposable DB с суффиксом `_test`.

```sh
# Repo root; отдельный venv, без общей environment другого проекта:
python3 -m venv .local-tools/cloud-check/venv
uv pip install --python .local-tools/cloud-check/venv/bin/python \
  --no-deps -r backend/requirements-dev.lock
.local-tools/cloud-check/venv/bin/python -m pip check
# backend/, при настроенной только disposable PG:
RUN_POSTGRES_TESTS=1 python -m pytest -q -p no:cacheprovider
python -m alembic upgrade head
# frontend/, pnpm 11.25.0 / Node 24.19.0:
corepack pnpm install --frozen-lockfile
corepack pnpm typecheck
corepack pnpm test
corepack pnpm build
# Против собственного loopback API/frontend и установленного Chromium:
CRM_BROWSER_BASE_URL=http://127.0.0.1:5173 corepack pnpm test:e2e
```

`python` backend-команд должен быть из указанного venv. В текущем запуске они
выполнены проверочным launcher с exact resource names и cleanup; это не инструкция
владельцу вручную запускать сервер. Исходные PowerShell-обёртки не использовались.

### Что PASS не означает

Не подтверждены этой проверкой: сборка Docker backend/frontend images и полный
Compose lifecycle, Nginx production-serving, постоянный volume/backup restore,
физические Safari/iPhone/Android и установка PWA. Browser suite работал с Vite
dev; отдельная production build прошла, но её Nginx deployment не запускался.
Полнота сравнения GitHub с исходной Windows-копией также не проверена.

В исходном LNAuto ещё нет авторизации, клиентов/автомобилей, рабочего календаря,
заказ-нарядов, складских/финансовых операций и QWEP. Это **рабочая техническая
основа для ограниченной облачной разработки**, не готовая рабочая CRM/MVP.
Бизнес-этап 2 этой проверкой не разрешён; его роли/правила остаются отдельной задачей.

## Ваниль: точный подтверждённый блокер

Из exact HEAD C2 прочитаны AGENTS.md, package.json, CLOUD_RUNTIME.md,
CLOUD_C2_REPORT.md, CLOUD_SETUP.md и cloud-setup.sh. Предыдущий PARTIAL-отчёт не
принят за новое доказательство. По указанному в нём официальному URL выполнен
свежий TLS-verified GET:

```text
https://binaries.prisma.sh/all_commits/0edf323efd1d98336f3f0a68684b56f689b900d3/debian-openssl-3.0.x/schema-engine.gz.sha256
```

Результат: **HTTP 403**, Content-Type text/plain. Повторный ограниченный запрос
использован только для диагностики отказа, не запуска setup. Текущий runtime
сообщает HTTP policy `unrestricted/enforced`, observations_current=true;
network_diagnostics отсутствуют. Происхождение 403 — proxy или upstream —
не установлено. Поэтому нельзя обещать, что простое добавление домена в allowlist
решит проблему. Credential для этого публичного engine не запрашивался.

Создание user/network namespace (`unshare --user --map-root-user --net true`)
в текущей среде разрешено. Это не полный тест cloud-isolate/runtime lifecycle.

После отказа preflight полный setup/install/generate/build/offline/Prisma DB
lifecycle и API/auth/frontend smoke **не запускались**: C2 требует остановки при
access denial. TLS/checksum, auth, scope, packageManager и lock не ослаблялись;
другой engine/mirror и незащищённый runtime не подставлялись. Существующий Draft
PR #1 и исходники не менялись; предыдущие 668/33/4 не считаются текущим результатом.

Минимальное условие продолжения — подтвердить доступ к этому официальному
checksum и соответствующему engine в поддерживаемой cloud environment. Затем
из exact C2 checkout запускать исходные cloud-setup/offline/DB/smoke команды.
Бизнес-код не следует менять для маскировки проблемы доставки engine.

## Следующий безопасный шаг

Ограниченная техническая разработка LNAuto теперь имеет фактическую Linux-базу.
Её можно продолжать отдельной разрешённой задачей из GitHub, сохраняя Windows-копию
для сверки и не вводя рабочие данные. Ваниль сохраняет конкретный внешний blocker;
Capital Lab пока остаётся нижним приоритетом. Автоматический coding-agent Commander
не получил write/grants к этим репозиториям. VPS/F33 продолжаются отдельно после
подтверждённого доступа владельца; текущая проверка их не возобновляет.
