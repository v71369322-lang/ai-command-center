# Расчёт ресурсов и расходов — не измеренная ёмкость

Панельные 4vCPU/8GB/80GB достаточно **в принципе** для одного ограниченного
synthetic executor, если OS audit/cgroup/quota/latency это подтвердят. Это не
гарантия NVMe IOPS, CPU share или свободных ресурсов. No load tests сейчас.
Сборки/CI остаются в cloud; не npm/pip/image builds параллельно рабочему PG на VPS.

## RAM/CPU/PID budget — DERIVED

| Группа | RAM envelope | CPU ceiling | Примечание |
| --- | --- | --- | --- |
| PostgreSQL | 1024 MiB | 1 | Начальный buffer/work_mem проверить отдельно; не tune blindly |
| Redis | 128 MiB, maxmemory64MiB/noeviction | 0.25 | Не source of truth; backlog восстанавливается из Outbox |
| API/static web | 256 MiB | 0.5 | PID64, tmpfs16MiB |
| Worker + broker | 384 MiB | 0.5 | PID64+32, не arbitrary coding agent |
| One executor | 128 MiB | 0.5 | PID32, tmpfs16MiB, no swap, fsize64KiB/output64KiB |
| VPN/HTTPS/MFA | 512 MiB aggregate | 0.25 | Реальный footprint Authelia/proxy уточнить |
| Watchdog + backup | 512 MiB aggregate | 0.5 | Restore job отдельно, не одновременно с executor |
| Total service envelopes | **2944 MiB** | **3.5** | Суммарные ceilings, не measured utilization |

Оставшиеся ~5GiB покрывают OS/page cache/runtime/операционные резервы; GiB и
панельные GB различаются. Rootless parent cgroup runner≤512MiB/1CPU/96PIDs;
child limits действуют внутри этого envelope. PG/backup/monitoring reserve не
занимать дополнительными исполнителями. Конкурентность=1, max_attempts=2,
wall30s/lease15s — fixed synthetic profile, не новая общая гарантия.

## Диск: план для nominal80GB, проверить фактический available/inodes

OS/packages≤12GiB; app images/rootless layers≤8; PG≤4; WAL/spool≤4;
service/security logs≤2; local encrypted evidence/spool≤2; temp≤2;
**не менее20GiB свободно**. Остаток — запас/разница GB-GiB, не permission заполнить.
Quota для rootless data-root/PG/logs, bounded image cache и защиту inodes проверяет
host audit. Не global prune, не удалять чужие images/тома/журналы. Cleanup только
known terminal synthetic run после сохранения evidence.

Service logs local driver10MiB×3 на сервис; journald общий cap256MiB/disk reserve
проектируется отдельно. Долговременные protected audit records — PG+offsite;
log rotation не удаляет их ради места. Удаление Git revisions/approved artifacts
требует учёта воспроизводимости. Мониторить free bytes+inodes, WAL lag, PG size,
OOM, cgroup throttling, pressure/load и stale services.

Предлагаемый admission warn при free<25GiB, stop optional starts<20GiB, emergency
incident<10GiB; MemAvailable<1GiB warning, <512MiB block optional starts. Не убивать
PG автоматически по числу loadavg. Порог/длительность стабилизации надо проверить
в controlled VPS trials, без произвольного увеличения лимитов исполнителем.

## Бюджет: плановые резервы, не тарифы

| Вариант | Новые обязательства | Что подтверждено |
| --- | --- | --- |
| Только текущий prep | **0 ₽ подключено** | Нет новых сервисов/аккаунтов; это не доказывает billing существующего VPS |
| Уже имеющееся разрешённое независимое хранилище/monitor | Может не потребовать новых платежей | Наличие, права, independence и retention неизвестны |
| Managed minimal offsite + dead-man | Плановый reserve **до1500 ₽/мес суммарно**, VPN отдельно если платный | Не quote: provider/курс/VAT/egress/object-lock/minimums ещё проверить |
| Дополнительный execution host/microVM capacity | Отдельный расчёт и approval | Сейчас не нужен по умолчанию и не арендуется |

Текущие расходы VPS, налоги/резервное хранение/трафик и применимость бесплатного
VPN плана **не подтверждены**. Нельзя вывести доступный остаток из факта покупки.
Перед каждым новым commitment: проверить фактическую цену, spent/reserved/forecast/
delayed billing; максимальное резервирование, срок/currency/caps, owner approval.
10 000 ₽/мес — hard ceiling, не разрешение купить до этой суммы. 70% warn,
90% restrict optional, 100% block nonessential; essential safety reserve нужен
заранее, не скрытое превышение ceiling. Если защищённый external backup не
помещается в разрешённый budget — deployment gate, не отключение backup.
