# Критический аудит F1: полное состояние PR #8 + PR #9

## Источники, метод и независимость

PR #8: `ea7a580e1bdf176bd5a8e9f29029e17411f695f8`.
PR #9: `4cadfb5046010e99c0632b0c41eb530a048100c5`, descendant PR #8;
оба PR открыты и не объединены на момент проверки. Ветка аудита
`audit/f1-full-system` начинается с PR #9, без копирования diff и без изменения
исходных веток. Аудит охватывает весь src/command_center, web, compose/Dockerfiles,
recovery/bootstrap, contracts, scripts/CI, tests и действующие границы F1.

Предыдущие отчёты не считаются доказательством отсутствия дефектов. Новые
регрессии сначала выполнены против исходной реализации, затем исправления.
Применены static inspection, threat scenarios, реальные PostgreSQL/Redis tests,
негативные API/browser проверки и sandbox fault tests в cloud.

Независимость от реализации **не подтверждена**: та же сессия ранее участвовала
в разработке. Этот отчёт — критический повторный аудит с воспроизводимыми
находками; он не закрывает требование внешнего независимого reviewer.

## Новые подтверждённые дефекты

| ID | Риск | Участок / воспроизведение | Исправление |
| --- | --- | --- | --- |
| FA01 | HIGH | Store.cancel: claim → cancel → повторный cancel/revoke переводил CANCEL_REQUESTED в CANCELLED, хотя остановка ещё не доказана; задача выпадала из active admission/reconciliation при удержанном reservation | Повторные отмены сохраняют CANCEL_REQUESTED; только остановка/reconciliation даёт terminal. Две регрессии проверяют reservation и блокировку параллельного claim |
| FA02 | MEDIUM | Store.retry: FAILED/verified_no_effect → halt → exact resume → owner retry оставлял прежнюю epoch; READY не исполнялась, approved_render не могла получить approval | Явный допустимый retry переносит только FAILED/no-effect задачу в текущую epoch, увеличивает version; approved_render требует свежего approval. Две регрессии, render и approved_render |
| FA03 | HIGH | Store.approve/claim/pulse/finish/retry не связывали task с Git revision создания. Store с другой source_revision мог одобрить/запустить/продлить/принять/повторить задачу прежнего кода | Проверка первой append-only task_created revision в PG под общим lock и после проверки audit chain. Пять регрессий. Смена build требует новой задачи/approval, не implicit consent |

**9 новых проверок упали на исходной базе; те же 9 прошли после исправлений.**
Это дефекты управляющей логики, не доказательство выхода из Docker sandbox.
Подтверждённых CRITICAL в пределах выполненных проверок не найдено; отсутствие
находки не доказывает отсутствие таких дефектов.

## Проверка всех областей A–F

| Область | Проверенные механизмы / тесты | Непроверенные границы |
| --- | --- | --- |
| A: isolation | Runner.command/valid_isolation, digest+revision image, no network/mount/socket, non-root/readonly/caps/NNP; реальные CPU/PID/OOM/file/tmpfs/output bounds | Kernel escape не исключён. Launcher socket даёт daemon authority. Host quotas/соседние workloads не проверены |
| B: authority | Server-side bearer roles, forged sender/unknown action deny, approval hash/version/epoch/expiry/revoke/use; operator не отменяет owner task; FA03 | Общий app DB role у API/worker не является независимым credential broker. Real owner identity/MFA отсутствуют |
| C: reliability | PG global admission lock, lease/fence, replay/idempotency/Outbox, real PG/Redis outage, running cancel, reconciliation, retries, FA01/FA02 | Не все scheduler/crash interleavings проверены. При потере worker нельзя обещать немедленную остановку orphan container без внешнего watchdog |
| D: integrity | Independent deterministic verifier (не import executor), forged/oversized/boolean-fence rejection, chain/UPDATE denial, corrupted pulse/finish, AES-GCM и isolated restore | Same-host checkpoint/key/backup не защищают от полного host compromise. Source label сам по себе не trusted artifact signature |
| E: API/web | Header auth без ambient cookie; no permissive CORS; cross-origin без bearer не останавливает контур; operator/agent IDOR mutation denied; browser HTML payload/result остаётся текстом; no-store/CSP, bounded body, logout in-memory token | Независимый pentest, VPN/HTTPS/MFA, DNS rebinding/доверие к reverse proxy и внешние порты требуют целевой проверки. Секрет в памяти браузера не безопасен при компрометации устройства |
| F: autonomy | Synthetic worker loop, bounded repair/attempt/time/budget, stop/revoke, deterministic allowlist, R-F1-AUTO-01 сохранено | Реального noninteractive coding provider нет по scope F1. Stage grants для реального разработчика и отсутствие platform prompts end-to-end не реализованы/не доказаны |

CSRF вывод относится к текущему bearer-header API без cookie auth. При добавлении
cookie sessions/CORS/proxy он требует новой проверки. Operator read visibility
общего single-owner state — текущая модель, не изоляция разных клиентов/тенантов.
Verifier независим по алгоритму результата, но не отдельный failure domain.

## Остаточные риски и gates

| Риск | Уровень | Статус / условие |
| --- | --- | --- |
| Trusted worker с Docker socket | HIGH | Подтверждённая архитектурная граница, не найденный executor escape. Только выделенный synthetic host/daemon; placement и недоступность socket недоверенным процессам обязательны до VPS trial |
| Host/DB admin переписывает chain/rollback без внешнего anchor | HIGH | Подтверждённое ограничение hash chain; нужна защищённая независимая custody checkpoint, offsite backup/key recovery и watchdog |
| Публичный web или ошибочная VPN/proxy/auth настройка | HIGH | Потенциальный deployment risk; только закрытый административный доступ, отдельные тестовые credentials, никаких public ports/real data |
| Worker потерян, контейнер живёт до восстановления контроля | MEDIUM | CPU/RAM/PID bounds есть; независимое прекращение по wall clock не доказано. Сверить orphan runs до новых запусков; проверить аварийный путь |
| Диск PG/logs и полное исчерпание ресурсов host | MEDIUM | Admission guards не заменяют host quota/monitoring; проверить в отдельном infra audit, не нагрузочным тестом сейчас |
| Обновление версии оставляет старые задачи | LOW | Намеренно fail closed после FA03; отменить старые и создать новые. Не переписывать creation event или отключать pin ради resume |
| Starlette/httpx deprecation | LOW | Не ошибка теста, отдельное обслуживание зависимости без подавления warning |

RPO ≤15 min/RTO ≤4 h — предварительные цели. Отдельный container restore на том же
cloud host не offsite drill. Реальных данных/провайдеров и продакшена нет.

## Воспроизводимость и результаты

Начальные focused tests: `scripts/cloud_test.sh -k test_audit_`:
9 failed до исправлений, 9 passed после (0.86 s), 64 старых теста deselected.
После этого добавлены API CSRF/CORS/IDOR проверки и усилен browser XSS сценарий.

Финальный полный профиль: `F1_BUILD_CA_FILE=/etc/ssl/certs/ca-certificates.crt scripts/verify_cloud.sh`
на clean tree `5133bd3e599c62e900bb83d1a8a101deeaceccf7`:
**75 passed**, 73.79 s, 0 failed/errors/skips; одна Starlette/httpx deprecation
warning. API/worker/PG/Redis/Outbox/approval/executor/verifier/web smoke,
restart/persistence/cancellation/new work, isolated encrypted restore и runtime
boundaries: PASS. Ruff/contracts/TS/Vite/locked builds/secret scan: PASS.
pip-audit: 62 runtime/dev dependencies, 0 advisories; npm 0; Bandit 0 MEDIUM/HIGH,
16 reviewed LOW. Результат не перенесён из прежних PR. Runtime evidence остаётся
в ignored .runtime без публикации credentials/ключей/архивов. Последующий коммит
изменяет только документационные доказательства; CI проверяет итоговый PR ref.

## Заключение перед VPS

После исправлений код может быть кандидатом для **ограниченного synthetic trial**,
но один факт завершения read-only инфраструктурного аудита не разрешает запуск.
Нужны подтверждённый выделенный launch boundary/ресурсы, закрытый доступ,
аварийная остановка/сверка orphan jobs, план защищённых evidence/backup и отдельное
точное разрешение владельца на trial. Нельзя переносить launcher на общий daemon
с другими проектами или трактовать эту оценку как production readiness.

Полная приёмка F1 не закрыта: внешнее независимое review, offsite/key recovery/
checkpoint/watchdog и целевые инфраструктурные проверки остаются обязательными.
SSH/VPS/CRM, real data/API, paid resources, merge и deployment не выполнялись.
