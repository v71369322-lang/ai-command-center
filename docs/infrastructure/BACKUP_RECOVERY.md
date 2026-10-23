# Независимые backup, audit checkpoints и disaster recovery

## Целевая модель — DERIVED

PG authoritative → локальный bounded backup spool → encrypted offsite repository
вне VPS/provider failure domain. Отдельный backup agent с scoped DB backup role;
decryption/restore credential и retention admin отсутствуют у app/worker/executor.
Рекомендуемый future tool — pgBackRest (encrypted repository, WAL archive/PITR),
либо эквивалент с проверенной совместимостью. Это не установленная зависимость.
Существующий F1 pg_dump/AES-GCM toolbox остаётся для synthetic drills; он сам
по себе не реализует continuous WAL/PITR, external schedule или независимую custody.

Offsite credential должен иметь минимальные права записи/чтения конкретного prefix;
delete/retention changes — отдельный owner-held credential. Реальная совместимость
backup tool с append-only/versioning/object lock подтверждается испытанием.
«Секрет записи не может DELETE» не означает, что он не может перезаписать объект;
нужны server-side immutability/versions и проверенная retention. Зашифрованный
bucket в том же VPS не offsite; snapshot в том же провайдере не единственная копия.

Ключи: генерировать только после разрешения, не в чат/Git/logs; encrypt before
egress, ключ/restore recovery хранить отдельно в owner-controlled encrypted vault
с MFA и offline recovery copy. Online encryption key может быть украден при host
compromise: encryption не заменяет immutability и независимый access control.
Нельзя обещать cryptographic authenticity после компрометации всех signer keys.

Audit anchor: sequence/digest/source SHA/time/run manifest отправляется в
append-only external custody; внешний collector фиксирует receipt/freshness.
При восстановлении сравнивать с последним независимым receipt, не только цепочку
из самого backup. Missing/rollback/mismatch → halted/recovery, ручное расследование,
никаких automatic resume или слепого replay. Отмены, внесённые после backup,
сверяются с внешним action journal и реальным execution daemon.

## Расписание и контроль — предложения, не гарантии

| Контроль | Начальный профиль | При нарушении |
| --- | --- | --- |
| WAL shipping | continuous, archive_timeout ≤60 s при совместимой настройке | Проверять last successful external receipt и backlog, не только upload exit code |
| Anchor custody | ≤60 s и перед опасным checkpoint/release | Stale/missing → incident и запрет чувствительных действий |
| Backup | daily differential, weekly full; retention предварительно 14 days | Действительная ёмкость/тариф/object lock ещё OPEN |
| Freshness | warn age5 min, fail age10 min offsite WAL receipt | Ограничить новые задачи, не удалять backlog/evidence |
| Verify | daily catalog/checksum/decrypt sample | Corrupt/missing → incident и новая проверенная копия, не overwrite evidence |
| Restore | weekly synthetic isolated drill + после изменений backup/key/tool | Измерить полный доступ/загрузку/restore/reconcile, не лишь SQL import |

Защитить local spool quota и мониторить WAL/PG volume: при offsite outage WAL
может заполнить диск. Не удалять вручную WAL ради свободного места; controlled
admission stop, эскалация и план безопасного обслуживания. Backup, watchdog,
security reserve не выключаются ради дополнительных AI runs; потолок расходов
при этом не превышается молча.

## RPO ≤15 min / RTO ≤4 h

Текущий dump toolbox и один VPS **не обеспечивают эти цели**. Для RPO нужны
continuous WAL + независимый receipt/freshness alert + bounded outage response;
даже archive_timeout не гарантирует доставку. Actual RPO измеряется последним
восстанавливаемым verified offsite WAL, включая задержку, а не периодом таймера.
Если downtime/offsite lag превышает окно, заявить breach/UNKNOWN, не обещать RPO.

Предварительный RTO budget: доступ/решение30m + replacement resources60m +
restore60m + reconciliation/security45m + verification/owner15m = **210 min**,
30m reserve. Это оценка, зависит от размера DB, bandwidth, provider support,
key recovery и доступности владельца. Полная потеря VPS требует разрешения
на новый ресурс; без заранее разрешённого recovery budget/capacity 4h не гарантируются.
Текущая неисправность панели провайдера делает RTO особенно неопределённым.

## Полная потеря VPS

1. External watchdog сообщает outage, revoke exposed credentials по точному scope;
   никакой blind retry незавершённых задач.
2. Владелец подтверждает replacement/расходы и восстановление. Проверить host key,
   чистую ОС, правила доступа и источник exact trusted artifacts заново.
3. Получить backup + key из независимых мест, проверить каталог/hash/authentication
   и внешний audit anchor. Restore сначала изолированно, network deny.
4. Установить recovery/halt/new epoch, revoke pending approvals; сверить orphan
   runs, cancelled intent и реальное внешнее состояние. Старый build/source pin
   не переносит полномочия на новый build автоматически.
5. Проверить app/readiness/backup/monitoring/kill path; owner принимает точное
   возобновление. Production DB restore всегда с отдельным approval.

Никакие credentials, аккаунты, bucket или расписания в этом пакете не созданы.
