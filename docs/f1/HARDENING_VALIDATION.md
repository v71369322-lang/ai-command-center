# Hardening: выполненные проверки и acceptance boundaries

## Источник доказательств

Clean-source implementation: `54ba8d19e0fb21778959d122d2dfeaf05ec66a78`.
Команда: F1_BUILD_CA_FILE=/etc/ssl/certs/ca-certificates.crt,
PLAYWRIGHT_BROWSERS_PATH=/workspace/.cache/playwright, scripts/verify_cloud.sh.

- **115 passed**, 0 failed/errors/skipped, **112.30 s**; одна нескрытая
  Starlette/httpx deprecation warning. 75 прежних cases + 40 новых hardening cases.
- **32 offline infrastructure tests** отдельно: PASS (0.14 s).
- Ruff, OpenAPI contract check, TypeScript/Vite build, locked builds: PASS.
- pip-audit: **63 runtime/dev dependencies, 0 advisories**; npm audit0.
- Bandit: **0 MEDIUM/HIGH**, 23 reviewed LOW. Новые B404/B603/B607 — fixed local
  argv/Unix daemon без shell; B110 — failed audit/backup handling не выдаёт success
  receipt/полномочия; B105 — metadata/secret binding names, не пароли. Findings
  сохранены, не подавлены. Это не независимое code review или image CVE certification.
- Actual container API→worker→broker→PG/Redis→executor→verifier→web: PASS.
- Actual restart/persistence/cancel/new work: PASS.
- Actual worker SIGKILL→separate watchdog→confirmed container absence→exact
  resume for new tasks: PASS; failed task не перезапускалась.
- Runtime inspect: API/worker без Docker socket; worker без CLI/PG/admin/owner
  secrets; broker/watchdog non-root+readonly+cap-drop, scoped secrets: PASS.
- Isolated encrypted backup→different networkless PostgreSQL→recovery/audit:
  PASS, **7.082 s**; это не offsite/RPO/RTO proof.
- Compose rootless overlay parser/merge: PASS_CONFIG_ONLY. Verified worker secret
  scope, rootless-required mode и socket replacement, API oidc mode, bounded logs.

Runtime JSON/JUnit/сканеры остаются в ignored .runtime; никаких ключей/архивов/
credentials в Git. Последующий commit документации и усиленного restore assertion
не выдаётся за новый local full-source run; итоговый GitHub CI проверяет PR ref.

## Негативная матрица

| Сценарий | Фактическая проверка |
| --- | --- |
| Без approval / reuse | Broker admission WAITING_APPROVAL, one-use PG grant, duplicate submit не исполняет повтор |
| Другой Git build | Existing five source-pin cases + broker revision mismatch; signature/trust change четыре случая сначала FAILED, после исправления PASS |
| Expired lease / forged fence | Real sleeping container lease expiry + strict RPC fence/boolean rejection + existing stale-result tests |
| Repeated cancel / stop refusal | Actual cancel of sleeping run; two failed stop attempts оставляют CANCEL_REQUESTED/UNCERTAIN и block admission |
| Worker crash | Actual SIGKILL Compose worker при работающем executor; separate watchdog killed it and proved absence |
| PG outage | Real PG stop во время execution, stop/evidence сохраняются, после PG return нет false success |
| Redis outage | Existing actual Redis stop/publish-before-mark/Outbox replay tests сохранены; нового отдельного end-to-end Redis-chaos drill не заявлено |
| Audit corruption | Actual privileged synthetic DB tamper; active run stopped, pulse/finish не принимают result |
| Corrupt/missing/stale backup | AES-GCM/read-back/checksum/age/traversal/overwrite/quota checks + real new DB restore |
| Broker unavailable | UDS connection failure без direct-Docker fallback; new starts не выдаются |
| Forbidden container | Typed request forbids arbitrary fields/actions; real isolation/privileged metadata negative tests |
| Resource exhaustion | Actual RAM/OOM/CPU/PID/file/tmpfs/log rotation + unsafe RuntimeLimits rejection; no claim host-wide quota proof |
| Stop/resume | Exact epoch/checkpoint, no cancelled revival; runtime operator reconcile оставляет halted |
| Watchdog unavailable | Missing heartbeat denies start; loss during active execution stops it; idle worker loss recorded |
| Unauthorized admin | Synthetic/role tests + real RS256 fixture IdP, no-MFA/wrong owner/audience/time/signature deny; HTTPS/session/CSRF/revoke tests |

## Исправлено во время реализации

1. In-flight create absence нельзя было считать stop proof на следующем tick:
   monotonic observed-start, launch lock и UNKNOWN interlock.
2. Concurrent broker/watchdog ledger bootstrap: atomic file creation и serial DDL,
   startup race regression (8 concurrent initializations).
3. Session survived owner/issuer/audience/JWKS change: 4 reproduced failures →
   trust-bound sessions из того же key snapshot, которым проверен JWT.
4. Restore дополнительно отзывает owner sessions; isolated real DB assertion
   проверяет непустую таблицу сессий и отсутствие active sessions после restore.
5. Worker больше не получает shared SQL credential или Docker socket; отрицательные
   SQL tests проверяют именно PostgreSQL42501, не просто произвольную ошибку.

## Не закрытые gates

Rootless host UID/cgroup/kernel/quotas, provider recovery, VPN/HTTPS/actual IdP и
реальный iPhone flow, external watchdog/alerts, offsite immutability/key recovery/
WAL-PITR, полный disaster recovery, independent review. Broker и local watchdog
по-прежнему доверены в пределах одного daemon/host. Rootful cloud mode нельзя
переносить на VPS как «проверенный rootless».

К ограниченным synthetic VPS trials — только после отдельного аудита, доказанного
launch/access/emergency boundary и отдельного owner разрешения. Full F1 acceptance
и production readiness не заявлены. VPS/CRM/real APIs/data/paid resources/merge
не использовались.
