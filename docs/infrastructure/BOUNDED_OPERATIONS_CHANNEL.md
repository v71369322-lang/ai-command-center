# F33: ограниченный повторно используемый канал операций

Код основан на PR #28 (`8723e10`), а не на main. Это отдельный Draft PR.
Фактически работающая версия VPS остаётся PR #26, `316dc16`, live bundle
`0ee8a6023296fdacfe632c2f364c488b2564db399bfd15af357812e41004d64b`.
Журнал её установки и реального Telegram находится в ops/f32-telegram-prepare:
[F32_LIVE_VALIDATION.md](https://github.com/v71369322-lang/ai-command-center/blob/ops/f32-telegram-prepare/docs/infrastructure/F32_LIVE_VALIDATION.md).
Этот этап не устанавливает новый канал и не меняет работающий VPS.

## Что выполняет код

`operations_channel.py` принимает только `status` и `update` через файловый
mailbox. Runner не запускает Docker, не получает sudo, credential bindings,
ключ подписания, private state или произвольную серверную команду.

Root-owned policy задаёт точные готовые bundle digests, их каталоги и Git SHA,
срок полномочий (не более 7 суток), до 256 операций и до 10 обновлений.
Digest политики входит в каждый запрос. Замена политики отзывает непринятые
запросы прежнего этапа. Каталог задаёт владелец; runner не может добавлять пути,
репозитории, переменные окружения, mounts, команды или releases.

Trusted operator работает как acc-control, используя существующий Deployment,
обе rootless daemons и прежние backup/quiesce/postcheck. Это административный
компонент хоста с существенными полномочиями, не sandbox AI-исполнителя.
Deployment проверяет expected predecessor внутри существующего deployment.lock:
ручное обновление, выигравшее гонку, блокирует устаревший удалённый запрос.

Канал разрешает только уже подготовленные пакеты. Он отвергает смену схемы,
PostgreSQL/Redis image, UID, data-root, способа входа или Telegram owner/bot/mode.
Реальные AI, CRM, GitHub credentials, init-state, rollback, reboot, установка
пакетов и изменение firewall отсутствуют в протоколе.

## Повторы, неопределённость и доказательства

- Строгий JSON без лишних/дублирующихся полей; UUIDv4, срок запроса до 15 минут.
- Проверки политики и срока повторяются после preflight, перед durable admission.
- SQLite WAL/FULL хранит intent до вызова Deployment. Один flock сериализует
  операции. Exact replay возвращает сохранённый результат без нового update.
- SIGKILL/timeout/потеря процесса после admission оставляет UNCERTAIN. Любое
  неопределённое обновление блокирует дальнейшие update даже при новой политике.
  `status` остаётся возможен. Автоматического повтора, restart update или отката нет.
- Журнал хранит hash chain и проверяет проекцию операций. Потеря уже созданной
  базы не начинает новую историю; локальный marker блокирует такой reset.
- Отдельный Ed25519-ключ подписывает квитанции. Private key — только в 0700
  каталоге оператора. Runner проверяет подпись системным OpenSSL, без Python
  зависимостей приложения. Public key сверяется с enrollment receipt владельца.
  Зелёный job или произвольный текст workflow сами по себе не доказывают эффект.

Signer, broker, даemons и private journal находятся на том же VPS и в trust
domain acc-control. Это не удалённая аппаратная аттестация и не защита от
компрометации trusted operator/root/его Docker daemon. Локальную hash chain
нельзя считать внешним неизменяемым checkpoint или независимой резервной копией.

## Ограничение ресурсов

Persistent runner: 512 MiB, 1 CPU, 256 tasks, MemorySwapMax=0. Код и registration
files read-only в service namespace. `_work` (512 MiB), `_diag` (16 MiB), `/tmp`
(64 MiB) и `/var/tmp` (16 MiB) размещаются в отдельных tmpfs; суммарную RAM
ограничивает cgroup. Host disk для произвольных job files не открыт. Вывод
демона не используется как неограниченный host log; job logs остаются в GitHub.

Общий inbox — отдельный tmpfs 1 MiB, nodev/nosuid/noexec, с максимумом 64 entries
и 16 KiB на запрос. Непринятый запрос может потеряться после reboot: это ещё не
подтверждение выполнения. Durable admission и подписанные receipts находятся
на постоянном диске. Повтор сохраняет исходные operation ID и payload; потеря
ответа не является разрешением создавать новую update-операцию.

Operator: 512 MiB, 1 CPU, 128 tasks, 15-minute timeout. Лимиты его процесса
не подменяют resource limits отдельных rootless Docker daemons/контейнеров.
Прерванная операция остаётся неопределённой; systemd не повторяет update.

## Один раз после отдельного разрешения установки

1. Владелец утверждает итоговый проверенный source SHA, bootstrap SHA-256,
   каталог разрешённых bundle digests и срок этапа. Секретов в каталоге нет.
   Пример сейчас диагностический: единственный действующий bundle, max_updates=0.
2. Доставить исходники через существующий одноразовый GitHub bootstrap runner.
   Не использовать новый production workflow до регистрации нового канала.
   `enroll.py` сначала копируется в root-owned snapshot и проверяется по SHA-256;
   root не выполняет скрипт непосредственно из runner-writable checkout.
3. `enroll.py --source CHECKOUT --approved-source EXACT_SHA --catalog-file FILE`
   по умолчанию только проверяет Git objects и печатает plan/catalog digest.
   Незакоммиченные файлы checkout не копируются. Проверяются также tree hashes,
   а не только blob hashes; Git работает как runner, не как root.
4. Только отдельный `--install --approved-catalog EXACT_DIGEST` на brain1 создаёт
   новый root-owned immutable operator package, policy, ключ и systemd units.
   Требуются прежние UID 1000/1001, отдельный runner без supplementary groups,
   VERIFIED baseline и неизменённый requirements.lock. Existing paths блокируют
   повтор вместо перезаписи. Работающее приложение и его Docker не меняются.
   Установка не регистрирует runner, не включает units и ничего не скачивает.
5. Один свежий GitHub registration token вводится скрыто в доверенном SSH TTY,
   никогда не в чат/argv/Git. Регистрация persistent: без --ephemeral, с
   --no-default-labels --labels acc-ops-mailbox --disableupdate.
   Старый one-job runner должен быть завершён. У него и нового unit Conflicts.
6. Администратор отдельно запускает/enable tmpfs mount, operator timer и новый
   runner service. Pin public key/policy digest из enrollment receipt в доверенном
   облачном контексте; проверить `status` и отрицательный запрос вне каталога.

Runner package остаётся read-only. Поэтому обновление официального runner —
отдельная плановая операция владельца. Обычные ограничения GitHub на устаревшую
версию действуют; --disableupdate их не обходит. Проверить принятие версии
GitHub и регистрацию/запись diagnostic logs до объявления канала рабочим.
Labels — маршрутизация, не запрет запуска другого workflow. Репозиторий должен
оставаться приватным с доверенными writers; untrusted PR не получают этот runner.
Даже произвольный job от его UID не должен пройти root policy или подделать receipt.

## Повторное использование

Будущая ветка ops/bounded-vps-requests содержит не секрет, а pending_request.json:
`{"request":{...},"receipt_public_key":"PINNED_PUBLIC_KEY"}`. Поля request:
schema=1, operation_id, policy_digest, action, target_bundle, expected_bundle,
issued_at/expires_at (целые Unix seconds). Один UUID и payload сохраняются при
неопределённом ответе. Ни branch name, ни текст задания не становятся командой.

Workflow запускает облачную проверку запроса. Только явный commit marker
допускает mailbox job на acc-ops-mailbox, который использует root-owned submit.py.
Ветка этого PR не запускает VPS jobs. Ни нового runner, ни queued host job
этим PR не создаётся. Нельзя направлять сюда произвольные PR/test jobs.

Новые исходники/сборки, migration или изменение Telegram credential binding
этот канал сам не готовит. Новый bundle должен пройти существующую подготовку
и отдельное разрешение этапа/каталога. Поэтому полная автоматическая доставка
любых будущих доработок без SSH ещё не объявляется реализованной.
Отзыв на хосте: остановить timer для новых операций; текущую операцию сначала
сверить с durable intent. Принудительная остановка допускает UNCERTAIN, не success.

## Проверки

Тесты используют настоящие файлы, SQLite, Ed25519/OpenSSL, конкурентные потоки
и SIGKILL отдельного процесса. Backend обновления — явный synthetic backend;
реальные backup/quiesce/update проверяются существующими deployment regressions.
Новый Ubuntu 24.04 container proof использует разные настоящие UID 1000/2000,
network=none, readonly rootfs и только capabilities для создания тестовых UID/
ownership и сброса привилегий. Docker socket не монтируется. Проверяется запрет
чтения private key/runtime placeholder, изменения policy/receipts, подписанный
roundtrip и exact replay. Это не запуск systemd/rootless/reboot на настоящем VPS.

Итоговые количества, warnings и ссылки CI публикуются в PR; пересекающиеся
targeted/full suites не суммируются. Host enrollment, mount/systemd compatibility,
persistent registration, quotas, restart и реальный update этого канала остаются
непроверенными до отдельно разрешённой установки.
