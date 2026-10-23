# T01–T14: проверяемый статус F1

См. [границы](SECURITY.md), [запуск](README.md), [restore](RECOVERY.md).
Результаты конкретного прогона — [VALIDATION](VALIDATION.md). Статусы ниже
разделяют пройденный cloud subset и **ещё не пройденную полную приёмку группы**.
Никакой pending пункт не считается PASS. Owner F1 acceptance отсутствует.

| Группа | Cloud-проверка | Статус полной группы / остаток |
| --- | --- | --- |
| T01 | API simulator → real PG/Outbox → Redis → Docker executor → independent verifier → shared API projection | ПРОЙДЕНО в cloud, включая Chromium 390px; целевой закрытый доступ отдельно T13 |
| T02 | Верный/поддельный/oversized результат, digest и реальный Docker-run | ПРОЙДЕНО для фиксированного JSON→Markdown адаптера; не real AI |
| T03 | Новый Store/process connection читает durable состояние; PG restart сохраняет задачи | ПРОЙДЕНО для cloud-сценариев; не VPS crash/power loss |
| T04 | Реальные stop/start PG и Redis, crash after publish до PG mark, lease/reconciliation | НЕ ПРОВЕРЕНО полностью: вся crash-window матрица и длительные disconnect tests |
| T05 | Idempotency conflict, concurrent claim, lost queue recovery, bounded Outbox rows | ПРОЙДЕНО для cloud-сценариев; exactly-once не обещается |
| T06 | Однократность, expiry/revoke/params/version/epoch; stale callbacks | ПРОЙДЕНО для synthetic identities; не real accounts/MFA |
| T07 | Agent/operator deny, forged sender, known-secret rejection, attributable denial | ПРОЙДЕНО для synthetic roles; независимое security review ожидается |
| T08 | Фактические UID/rootfs/network/mount/capability границы; path/unknown action/prompt injection | НЕ ПРОВЕРЕНО полностью: полномочия trusted Docker launcher и полноценный adversarial review |
| T09 | Pending cancel, реальный running-container cancel, stop/точный resume без revival | ПРОЙДЕНО для cloud-сценариев; disaster recovery resume отдельно заблокирован |
| T10 | Реальные OOM/file/tmpfs limits; измеренная CPU/PID изоляция; бюджет/attempt/step/admission bounds | НЕ ПРОВЕРЕНО полностью: quota хоста и полный resource exhaustion |
| T11 | Hash chain, app DB UPDATE denial, tamper/truncation against checkpoint | НЕ ПРОВЕРЕНО полностью: независимая защищённая custody checkpoint |
| T12 | Настоящий pg_dump/pg_restore, AES-GCM corruption rejection, old-backup interlock | НЕ ПРОВЕРЕНО полностью: offsite custody, key recovery, WAL/PITR, полный RPO/RTO drill |
| T13 | Auth/RBAC, CSP/no-store, body-size including chunked; loopback configuration | НЕ ПРОВЕРЕНО полностью: VPN/HTTPS/MFA и внешняя проверка портов; мобильный browser проверен |
| T14 | Ruff, TS/Vite, locked dependencies, container build, pytest, pinned image/action refs | НЕ ПРОВЕРЕНО полностью: remote trusted CI outcome, reproducibility across clean hosts, independent review |

Критические нарушения блокируют приёмку. «Не проверено полностью» не означает,
что тест падал: это отсутствие требуемого полного доказательства. Если тест
упадёт, статус его поднабора — НЕ ПРОЙДЕНО до исправления и повторной проверки.

## Оставшиеся blockers

- Независимое review значимого изменения и trusted CI evidence.
- Полные fault/adversarial/mobile-browser/resource suites.
- Разрешённая независимая custody backup/checkpoints и key recovery, watchdog.
- Проверенные recovery-resumption runbook и resource/rate/circuit hardening.
- На VPS: отдельные разрешения, host-key/access, audit, launcher boundary,
  actual quotas, закрытый web/MFA, offsite restore и owner acceptance.

Обычные коммиты/тесты/исправления внутри текущего облачного этапа разрешены;
SSH, реальные системы/данные, новые платные обязательства, merge и следующие
этапы не разрешены. Полная приёмка F1 не объявлена.
