# F1 infrastructure hardening: реализация и границы доказательств

База PR #11: `7ab8a4f467bfe8f98f105c909bd26dae6267721c`, ветка
feat/f1-infrastructure-hardening, PR target infra/f1-vps-preparation. Зависимые
PR не объединяются; исторические решения не переписываются. Изменения разрешены
текущим поручением владельца «F1 INFRASTRUCTURE HARDENING».

## Реализованный execution path

Worker → authenticated Unix RPC → runtime broker → authoritative PG claim/
approval/source/lease/fence checks → fixed Docker command → independent verifier.
Worker image не содержит Docker CLI, не монтирует Docker socket, DB или owner
credentials. Broker имеет отдельный f1_runtime PG role: не создаёт approvals,
не меняет payload/версии и не читает owner_sessions. Bootstrap запрещает inherited
roles и очищает старые grants перед выдачей узких прав. Worker вообще не имеет PG
credential, поэтому не может подделать owner approval через SQL.

RPC model: submit(task UUID, exact source SHA), status/heartbeat(task UUID,
strict integer fence) и worker_online(exact source SHA) без task authority.
Extra fields/неизвестные действия/oversized body/неверный
token отклоняются. Нет raw Docker JSON, image/mount/shell/network выбора от worker.
Image выбирает только trusted broker configuration; immutable ID и source label
проверяются перед запуском. Trusted CI/provenance на целевом хосте остаётся gate.

RuntimeLimits загружаются F1_LIMIT_* из trusted environment, с проверенными
диапазонами. Defaults: one concurrent execution, 0.5CPU/128MiB/32PIDs/16MiB tmpfs,
wall30s, output64KiB, file64KiB, logs1MiB×2, min-free256MiB, bounded2 stop attempts.
Типизированный запрос не может увеличить их. No network/host mounts/privileged,
nonroot65532, readonly rootfs, ALL caps dropped и no-new-privileges обязательны.

## Rootless и доверенная граница

RuntimeBackend по умолчанию требует rootless Docker + cgroup v2/systemd, только
allowlisted local Unix endpoint. Rootful daemon отклоняется. В текущем cloud нет
доступных Podman/rootless tools, поэтому действующий compose.yaml — явно
**cloud-rootful-test**, только для изолированного облачного лабораторного daemon.
compose.rootless-required.yaml принудительно включает rootless и fail-closed
OIDC auth; не устанавливает daemon/VPN/IdP и не является VPS deployment proof.
Реальное rootless UID mapping, cgroup enforcement, quotas и kernel/runtime защита
не доказаны этим профилем. Произвольный AI-generated код сюда не добавлен.

Broker и отдельный watchdog — trusted runtime TCB. Watchdog использует тот же
dedicated runtime непосредственно, чтобы отказ broker RPC не лишал его stop path.
Это обоснованное изменение прежнего DERIVED плана stop-only shim: внешнего raw
Docker proxy всё равно нет, но credential watchdog даёт весь доступ к daemon,
не криптографически stop-only. На rootful cloud daemon это host-level authority;
на выделенном rootless daemon — authority его UID/контейнеров. Нельзя считать
socket безопасным из-за доверенного имени сервиса. API/worker/executor socket не
получают. Host/runtime failure остаётся общим failure domain.

## Watchdog и восстановление

runtime_ledger — fsynced SQLite с append hash-linked evidence и durable run
mapping; worker не получает volume. Heartbeat watchdog нужен для admission;
исчезновение watchdog также останавливает текущий broker run. Watchdog — другой
процесс/контейнер, не поток worker. Idle-worker heartbeat проверяется отдельно;
его потеря журналируется. Он проверяет wall/worker heartbeat/PG lease/
fence/cancel/halt/audit и bounded stop + actual absence/daemon health.

При stop refusal/неизвестном create: UNCERTAIN, reservation сохраняется, новые
starts запрещены. Признак observed_start монотонен: отсутствие контейнера при
INTENT никогда не превращается в доказанный stop даже на повторном poll.
Cross-process launch lock не даёт принять отсутствие во время in-flight launch.
Повторный cancel не теряет intent. PG outage не уничтожает local stop evidence.

После исчерпания попыток: trusted operator может вызвать
`python -m command_center.watchdog --reconcile-task UUID --fence N` только для
ранее наблюдавшегося run; команда подтверждает отсутствие и оставляет admission
halted, не выдаёт retry/resume. Неизвестный create требует отдельного расследования.
При reboot ledger не удаляется; активные/неопределённые runs блокируют admission
до сверки. Никакого automatic dangerous resume или полного удаления Docker state.

## Owner auth и мобильная панель

F1_AUTH_MODE=oidc использует PyJWT/RS256 с pinned local public JWKS, exact issuer/
audience/owner, expiry/not-before/iat/jti, recent auth_time и standard amr=mfa.
Нет собственного MFA протокола или обращения к настоящему IdP. Без настроенного
доверия exchange503 и protected API401; synthetic bearer не обходит OIDC mode.
HTTPS обязателен. Future proxy trust должен быть точно настроен, не wildcard.

Assertion одноразово обменивается на random256-bit server-side PG session:
только hash token/CSRF, Secure/HttpOnly/SameSite=Strict __Host-cookie, max900s и
не дольше assertion expiry. Unsafe actions требуют CSRF и совпадающий Origin,
cross-origin CORS не открыт. Logout/revoke-all/expiry закрывают доступ, события
сессий и административных действий журналируются. Restore отзывает owner sessions.
CSRF после reload восстанавливается через protected same-origin endpoint.
UI не хранит credentials в localStorage, умеет exchange/session/CSRF/logout;
асинхронное обновление после смены credential не возвращает старое состояние.

MFA реально выполняет будущий IdP; tests используют ephemeral local RSA fixture.
Redirect/enrollment/HTTPS/VPN/recovery codes/реальный iPhone ещё не подключены.
Это работающий adapter, но **production access не готов**. Synthetic mode сохранён
только для существующих cloud-сценариев и явно подписан в UI.

## Backup jobs

backup_jobs: настоящий PG dump → AES-256-GCM envelope с source/time/checkpoint/
dump hash → immutable-name repository put → read-back/decrypt/hash verification
→ successful receipt. Status проверяет age/corruption/missing/clock anomalies;
failure не создаёт свежую success receipt. Restore в новую f1_restore_* DB
проверяет anchor, затем halted/recovery/new epoch/revoked approvals/sessions.
Export checkpoints пригоден для внешней custody/проверки existing audit chain.
Backup/restore successes и failures журналируются без ключей/сырого exception.

Repository Protocol — граница внешнего storage; LocalRepository реально работает,
с quota/lock/no overwrite/path traversal/size limits/fsync, но **не offsite**.
External account/service, WAL/PITR, protected immutable custody и полный RPO/RTO
не подключены и не объявлены достигнутыми. Timer/service examples предназначены
для будущего отдельно разрешённого host installation, сейчас не установлены.

## Проверка

scripts/verify_cloud.sh включает прежние security/fault tests, новые broker/
watchdog/session/backup tests, реальный container API→worker→broker→executor,
restart/new work, worker SIGKILL drill, isolated restore и runtime mount inspection.
CI добавляет 32 offline infrastructure tests. Новые результаты публикуются только
после фактического clean-source прогона; предыдущий PASS75 не заменяет его.

SSH/VPS/CRM, реальные данные/AI/Telegram/IdP/storage/alerts, paid resources, merge
и production не выполнялись. Полная приёмка F1 требует owner acceptance и ещё
открытых host/offsite/independent-review gates.
