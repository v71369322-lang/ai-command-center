# T01–T14: проверяемый статус F1

Основание: [VALIDATION.md](VALIDATION.md), 64 теста после ревью и завершённый контейнерный
профиль. PASS относится только к описанной cloud-проверке. Непроверенные условия
не считаются пройденными. Owner acceptance отсутствует.

| Группа | Cloud-проверка: ПРОЙДЕНО | Остаток / НЕ ПРОВЕРЕНО |
| --- | --- | --- |
| T01 | Simulator → API → PG/Outbox → Redis → executor → verifier → web; Chromium 390px | Целевой закрытый доступ на VPS |
| T02 | JSON→Markdown, hashes, forged/oversized result, строгий тип fencing | Реальный AI намеренно вне F1 |
| T03 | Durable state, PG restart, API/worker restart и новая задача | VPS power loss |
| T04 | PG loss во время executor, Redis restart, publish/crash window, reconciliation, bounded backoff/circuit breaker | Все crash windows и длительные outages не доказаны |
| T05 | Duplicate/conflict, concurrent claim, fencing, lost queue recovery, Outbox replay | Exactly-once внешние эффекты не обещаются |
| T06 | Exact action/version/hash/epoch, expiry/revoke, одноразовость, forged/stale denial | Реальные аккаунты/MFA |
| T07 | Synthetic owner/operator/agent RBAC, forged sender, secret rejection, denial audit | Независимое review кода |
| T08 | UID/rootfs/network/mount/capability; path/unknown action/prompt injection; API без socket | Trusted launcher имеет Docker socket; VPS boundary и independent adversarial review |
| T09 | Pending/running cancel, expired lease cancellation, stop/resume, отсутствие revival после restart | Disaster resumption не разрешён |
| T10 | CPU/PID/OOM/file/tmpfs ограничения, admission/step/attempt/rate/budget bounds | Host quota и полное resource exhaustion VPS |
| T11 | Hash chain, app-role UPDATE denial, tamper/truncation against checkpoint | Независимая защищённая custody checkpoint |
| T12 | AES-GCM, dump/restore, отдельный networkless PostgreSQL, old-backup interlock | Offsite custody, key recovery, WAL/PITR, полный RPO/RTO drill |
| T13 | Auth/RBAC, CSP/no-store, chunked body bounds, actual loopback binding, mobile browser | VPN/HTTPS/MFA, внешняя проверка портов |
| T14 | Ruff, TS/Vite, contracts, pinned/locked builds, 64 tests, security audits | Remote CI проверяется отдельно в PR; clean-host reproducibility и independent review |

Критическое нарушение блокирует приёмку. Непроверенный пункт не означает падение
теста, но не считается PASS. Независимое review, внешние backup/checkpoint и
watchdog, целевой закрытый доступ и host isolation остаются gates.
RPO ≤15 минут/RTO ≤4 часов — предварительные цели, не гарантии.

VPS audit/развёртывание требуют отдельных разрешений. SSH, реальные данные/API,
новые платные обязательства, merge и следующий этап не разрешены.
Окончательное завершение F1 подтверждает владелец явно.
