# Watchdog: два failure domain и безопасная остановка

## На самом VPS, независимо от worker/AI

Отдельный enforcer под supervisor/systemd с typed stop-only endpoint trusted
runtime shim, без raw Docker socket; durable run ledger/deadlines, fail-closed admission marker.
Timer проверяет run identity/fence/lease/deadline, PG readiness и host resources.
Не читать произвольный Docker label как полномочие; проверять ledger, daemon и
immutable image/run mapping. Не выдавать enforcer raw rootful/rootless socket.
Shim имеет полномочия всего dedicated rootless daemon: это trusted граница,
не доказанный stop-only Docker credential.
Реализация typed stop path/systemd units отсутствует; это future gate, не
уже работающая автоматическая защита.

| Событие | Безопасная реакция | Доказательство / после восстановления |
| --- | --- | --- |
| Worker heartbeat stale | Блокировать starts, проверить PG lease и точный run deadline | Independent enforcer останавливает только известный run; результат uncertain |
| PG недоступна | Запрет starts/lease renew, bounded stop текущего run | Ledger сохраняется вне Redis; reconcile до retry |
| Executor завис/wall deadline | Grace stop → kill → inspect stopped | Не считать stop API response доказательством отсутствия контейнера |
| Lease/fence lost | Stop obsolete run, reject late result | Старый fence никогда не фиксирует success |
| Docker stop невозможен | Halt, retain reservation/evidence, independent alert | Owner/admin emergency; никаких replacement runs |
| RAM/disk/PIDs low | Admission block, остановить optional workload в разрешённом профиле | Не останавливать PG/backup/monitoring вслепую и не чистить audit |
| Audit mismatch | Halt опасных действий, сохранить evidence, alert | Сверка внешних anchors и approvals; не пересчитывать цепочку ради PASS |
| API down | Health failure, local supervisor diagnostic | Не автоматический resume задач; проверка PG/queue/worker отдельно |

Начальные DERIVED thresholds: poll5s, heartbeat stale20s, run deadline30s;
задержки scheduler/DB/stop должны быть измерены. При потере доверия к clock,
ledger или boot identity — halt. Это не обещание остановки точно за эти секунды.
Wall deadline не продлевается worker pulse бесконечно. Repeated failures bounded;
потеря доступа к daemon не лечится выдачей новых admin privileges AI.

## Вне VPS/provider и AI providers

Независимый монитор хранит только scoped наблюдения, проверяет VPN/private health
через разрешённый путь и отдельный dead-man heartbeat/backup+anchor receipts.
Не публиковать admin API ради публичного uptime checker. Отсутствие receipt =
UNKNOWN/incident, не healthy. Внешняя проверка отличает outage от отказа самого
checker (его собственный heartbeat/alert delivery test).

Критические alerts владельцу через независимый канал (например согласованный
push/email), без AI/Telegram зависимости. Реальные сообщения/интеграции сейчас
не подключать. Внешний monitor **не держит unrestricted SSH**, production DB или
Docker credentials; может сигнализировать и отзывать только явно scoped rights.
Полный host compromise нельзя гарантированно остановить агентом на том же host.
Provider console/rescue и независимые backups/anchors обязательны. Permanent
second VPS не требуется по умолчанию: managed dead-man service/существующий
авторизованный независимый endpoint — варианты после проверки условий/цены.

## Reboot / падение процессов

DB/Redis/API допускается supervised restart только после инфраструктурной проверки,
но это не automatic task resume. В template restart=no намеренно: нет готового
boot gate. После reboot: admission disabled → storage/secrets/PG/audit ready →
сверка всех runs/leases/отмен/reservations → restore/incident interlock сохраняется
→ точное owner разрешение на resumption где требуется. Redis потерян — Outbox
replay из PG, не восстановление полномочий из сообщения. Cancelled tasks не оживают.

Drills на будущем isolated VPS: kill worker при живом executor; PG outage;
enforcer restart; stale lease; Docker stop failure; reboot; external monitor outage;
backup staleness; corrupted audit. Не выполнять эти воздействия в read-only audit.
