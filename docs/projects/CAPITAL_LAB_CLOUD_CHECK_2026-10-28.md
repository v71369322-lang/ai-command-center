# Capital-Lab: фактическая облачная проверка — 28.10.2026

Продолжение проверки трёх проектов после LNAuto и preflight Ванили. Только
существующий `v71369322-lang/Capital-Lab`; название CryptoLab из сообщения
владельца пока не сопоставлено с отдельным репозиторием. Среди четырёх доступных
репозиториев есть Command Center, LNAuto, Vanilla-Sugar-CRM и Capital-Lab.
Это не доказательство, что другого проекта нет; переименование/новый project ID
не выполнялись. Проверка не разрешает реальные инвестиционные операции.

## Источник и границы

- [Существующий Draft PR #1](https://github.com/v71369322-lang/Capital-Lab/pull/1):
  `codex/cloud-c2-linux-compatibility`, HEAD `0e1a16986baa5a217b2ec03d0db5146c51bb6f8a`.
- База PR: main `1b18e033e127b853fd95e32cab88053e719bfdab`. Проверялся HEAD C2/C3,
  не main с потерей Linux-изменений. Метаданные повторно сверены после тестов.
- Отдельный чистый detached checkout в cloud. **Все 306 tracked files совпадают
  с Git blobs**, `git status --porcelain` пуст; исходники/locks/ветки/PR/settings
  Capital-Lab не менялись. Клиентские данные и Windows не переносились.
- Debian 13.6 x86_64, uid 1000, Python 3.12.14, Node 24.19.0, pnpm 11.25.0.
  Использованы существующие C3 scripts без патчей и ослабления safety gates.

## Практически выполнено

| Проверка | Новый результат |
| --- | --- |
| `python3.12 scripts/cloud_runtime.py probe` | socketpair send/recv и loopback TCP PASS |
| `bash scripts/cloud_install.sh --with-postgres` | PASS: новый private venv, pinned requirements, frozen frontend install/build, локальные PG binaries |
| `bash scripts/cloud_install.sh --with-postgres --check` | PASS; версии, `pip check`, build и binaries проверены |
| `scripts/cloud_runtime.py smoke` | Настоящий HTTP: health 200, ready 503 без DB (ожидаемо), HTML Workbench и synthetic API 200 |
| `scripts/cloud_postgres.py validate --all` | **1414 passed, 13 skipped, 1 warning**, exit 0; offline + реальные PostgreSQL tests |
| HTTP с migrated temporary DB внутри validator | health/ready/HTML/synthetic API — 200 |
| Frontend Vitest | **138 passed / 18 files** |
| TypeScript / Vite production build | PASS; Vite 8.3.4 |
| `bash -n scripts/cloud_install.sh` | PASS |
| Cleanup / Git | Собственные PG/HTTP temp roots удалены, исходники не изменились |

PostgreSQL 17.11 (`17.11-0+deb13u1`) получена существующим installer из
официальной подписанной Debian trixie metadata. Два пакета извлечены локально;
maintainer scripts, system-wide package installation, Docker и systemd не нужны
и не использовались. Это user-local PostgreSQL, не проверка rootless Docker/VPS.

Validator создал новый приватный кластер на случайном loopback-порту, SCRAM,
роль `cl_test_app` без superuser/createdb/createrole/replication и две новые
disposable DB. Переданы явные `--allow-test-db-write --require-postgres
--require-asgi`; пропуск PG/ASGI не выдаётся за PASS. Случайные временные пароли
не публиковались. После завершения PostgreSQL остановлена; `/tmp/capital-lab-pg-*`
и `/tmp/capital-lab-http-*` отсутствовали. Постоянный сервер не оставлен.

Наборы не складываются: SQL tests входят в 1414, повторного отдельного SQL
прогона не было; HTTP checks не прибавляются к pytest. Нового GitHub Actions
run Capital-Lab не создавали — это текущая проверка в managed cloud.

13 skipped: 12 native Windows Crypt32/WinCred/trust/.NET checks и одна Tk GUI
проверка без DISPLAY (она остаётся BLOCKED). Один warning — прежний
Starlette/httpx deprecation. Эти условия не объявляются проверенными на Linux.

Изначальная отдельная frontend-команда использовала отсутствующий локальный
путь pnpm и завершилась 127 до запуска тестов. Исправлен только путь вызова на
Corepack/pnpm 11.25.0; приложение, packageManager и lock не менялись.

## Что работает и что не подтверждено

Подтверждён существующий Linux runtime: настоящее ASGI/HTTP, Workbench HTML и
synthetic API, SQL safety/migration gates, backend/frontend regression и build.
Расчётное ядро/локальные инструменты проверяются их тестами; это не новая
аттестация методов для реальных выпусков, актуальных котировок или торговли.
Блокеры документального real-bond пилота и права поставщиков не закрывались.

Не включались OpenAI, брокеры/MOEX/Finam/T-Invest, live/crypto execution,
синхронизация или уведомления. Реальные credentials/счета/портфели не читались;
новые данные — только собственные synthetic/temp. Постоянная cloud-конфигурация
в UI не менялась, setup hook для новой сессии не считается сохранённым.

Не проверены physical iPhone/Safari/Windows, browser UX/E2E Workbench,
production HTTPS/auth, VPS deploy/reboot/backup и постоянная multi-process
эксплуатация. Frontend build не выдаётся за мобильную UX-приёмку.

## Дальше по общему плану

1. Command Center: перед серверным продолжением сверить фактический F33
   enrollment, затем дать новую точную разрешённую операцию. Старое окно
   установки истекло; действующий канал управления VPS не подтверждён.
2. LNAuto: [Draft UI PR #1](https://github.com/v71369322-lang/LNAuto/pull/1),
   `6eb27e105f976130b9a7975517fc90504bdb1f9f`,
   [frontend CI SUCCESS](https://github.com/v71369322-lang/LNAuto/actions/runs/40718450230).
   В отдельном пилоте прошли 13 backend / 30 frontend / 12 browser;
   бизнес-этап 2 не начат. VPS deployment LNAuto не выполнялся.
3. Capital-Lab: cloud-техническая база подтверждена этим прогоном. Следующая
   продуктовая/финансовая задача требует собственного scope; реальный API,
   новые credentials, расходы и торговля автоматически не разрешаются.
4. Ваниль: ранее подтверждённый Prisma checksum HTTP 403 остаётся открытым;
   повторного запроса/обхода в этом прогоне нет. Не запускать три production
   проекта на VPS Commander из общего слова «подключить».

VPS/CRM, Windows, production, платные ресурсы, merge и deployment не затрагивались.
