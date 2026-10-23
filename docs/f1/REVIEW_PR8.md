# Повторное критическое ревью PR №8

База: `ea7a580e1bdf176bd5a8e9f29029e17411f695f8`, PR #8 открыт, не объединён,
base `docs/stage-0c-5-master-plan-audit`. Ветка `review/f1-security-autonomy`.
Это повторная проверка фактического кода, не доверие прежнему отчёту.
Ограничение независимости: текущая сессия участвовала в исходной разработке.
Отдельная ветка не делает reviewer независимым; внешнее review остаётся gate.

## Подтверждённые дефекты

| ID / риск | Воспроизведение на базе | Исправление |
| --- | --- | --- |
| RV01 / HIGH: потеря намерения отмены | claim → cancel → abort(stopped=False) давал RECONCILING; reconciliation затем FAILED/verified_no_effect, что после resume открывало owner retry отменённой задачи | abort сохраняет CANCEL_REQUESTED; неопределённый stop удерживает halt/reservation; reconciliation завершает CANCELLED, retry запрещён |
| RV02 / MEDIUM: recovery терял cancel intent | claim → cancel → enter_recovery давал RECONCILING | Recovery и отдельный restore drill сохраняют CANCEL_REQUESTED; исход после сверки — CANCELLED. Текущий recovery interlock уже блокировал resume, поэтому это latent recovery defect, не доказанный bypass текущего API |
| RV03 / MEDIUM: повреждённый audit после claim | claim → test-admin меняет audit digest → finish фиксировал SUCCEEDED | pulse и finish проверяют цепочку под admission lock; повреждение вызывает Denied до продления lease/фиксации результата. Требует привилегированного повреждения БД; обычный app role не может UPDATE audit. Это не защита от полного захвата host/переписывания всей цепочки |

Три регрессионных теста сначала выполнены против неизменённой реализации:
**3 failed**, подтверждены ожидаемые нарушения. После исправлений те же тесты:
**3 passed**. Для RV03 дополнительно проверяется pulse отдельным параметром.
Все данные synthetic; tamper только admin fixture собственной тестовой БД.

## Проверенные границы и остаточные риски

- Docker launcher: socket даёт полномочия daemon/host, non-root и cap-drop это
  не ограничивают. HIGH residual deployment gate уже объявлен исходной F1:
  launcher только в выделенной cloud-среде, не на общем VPS до отдельного audit
  и безопасного daemon boundary. Executor/API socket не получают. Нельзя
  переименовать launcher в sandbox или обещать независимую host isolation.
- Executor: фиксированный synthetic JSON→Markdown; no network/host mounts,
  readonly rootfs, non-root, caps drop, no-new-privileges, CPU/RAM/PID/tmpfs/file
  и output limits. Это не запуск произвольного реального coding agent.
- Approvals: server-side roles, action hash/version/epoch/expiry/revoke/use;
  очередь не выдаёт полномочия. PG admission lock и lease/fence остаются
  authoritative; cancellation/recovery исправлены без расширения scope.
- API/web: in-memory synthetic credentials, body bounds, RBAC, no-store/CSP и
  текстовый render. Loopback не равен VPN/HTTPS/MFA; нет доказательства реальной
  аутентификации владельца или защищённого iPhone-to-VPS доступа.
- Audit: append-only для app role + hash chain. При полном admin compromise
  возможна перепись/rollback без внешнего anchor. Независимая custody остаётся
  обязательной, не реализуется покупкой сервиса без разрешения.
- PostgreSQL/Redis: PG durable truth; transport duplicates и outages не означают
  разрешение blind retry. Синтетический reconciliation нельзя переносить на
  реальные необратимые эффекты. Circuit breaker process-local, не HA guarantee.
- Backup: AES-GCM и отдельный networkless restore container; тот же cloud host
  не offsite failure domain. Key recovery/WAL-PITR/полный RPO-RTO не доказаны.
- Secrets: runtime files вне Git, no admin/owner identities у worker, no secrets
  у executor; scanners не гарантируют отсутствия всех возможных утечек.

## Проверки и воспроизводимость

Полный профиль: `F1_BUILD_CA_FILE=/etc/ssl/certs/ca-certificates.crt scripts/verify_cloud.sh`
на clean tree. Он включает Ruff/contracts/secret scan/Python+npm audit/Bandit,
TS/Vite, locked builds, pytest, реальный API-worker smoke, restart/new work,
изолированное восстановление и runtime inspect. Результат финального прогона
зафиксирован: **64 passed**, 0 failures/errors/skips, 80.53 s; одна нескрытая
Starlette/httpx deprecation warning. Clean-tree revision:
`6855c6c1d982785fb11d161f8737690a8f743cdb`.
Контейнерный API/worker/approval/verifier/web smoke, restart/persistence/cancel/
new work, runtime boundaries и encrypted isolated restore: **PASS**.
Restore drill 9.72 s не доказывает offsite или RPO/RTO. Ruff, contracts, TS/Vite,
container builds и secret scan: PASS. pip-audit: 62 runtime/dev dependencies,
0 advisories; npm 0; Bandit 0 MEDIUM/HIGH, 16 reviewed LOW.
Прежний PASS PR #8 не использован как PASS новых изменений. Документационный
коммит после указанного source SHA не выдаётся за новый локальный code run.

Новая норма владельца: [R-F1-AUTO-01](../requirements/AUTONOMOUS_EXECUTION.md).
Диагностика подтверждений: [CLOUD_AUTONOMY.md](CLOUD_AUTONOMY.md).
PR исправлений должен сравниваться с веткой F1, а не включать весь F1 повторно.
Никаких SSH/VPS/CRM, real APIs/data, paid resources, merge или production.
