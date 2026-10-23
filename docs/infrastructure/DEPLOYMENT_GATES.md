# Последовательность, зависимости и отдельные разрешения

Текущий этап G0: подготовка файлов/документации/тестов в cloud. Он не разрешает
следующие этапы. Ordinary edits/tests/commits/PR внутри G0 автономны; никаких
per-command owner approvals в целевой модели R-F1-AUTO-01. Платформенные gates
не обходить, current global settings не менять.

| Gate | Работа после отдельного разрешения | Проверяемый результат / зависимости |
| --- | --- | --- |
| G1 access/read-only | Independent host key, защищённый credential, exact target/scope/time, cloud route; только аудит | OS/resources/services/network/rights report с PASS/FAIL/UNKNOWN; никакого install/restart/scan |
| G2 boundary implementation | В isolated cloud: typed broker/worker adapter, rootless backend, independent deadline enforcer, boot gate; MFA session integration | Negative tests no arbitrary Docker API/mount/privileged/network; worker-kill/deadline/daemon-loss/reboot scenarios; separate review/PR |
| G3 host preparation | Проверенные recovery console и backup имеющегося состояния, OS patching/accounts/rootless/cgroup/firewall/VPN/proxy/MFA по точному плану | Второй key login, no lockout, IPv4/IPv6 ingress/egress proofs, secret UID/mode, package/artifact provenance; owner approval на новые commitments |
| G4 independent safety | Offsite/versioned custody, keys/recovery, external watchdog/alerts, backup schedule | Missing/corrupt backup, anchor rollback, phone-loss и полной потери host drills; RPO/RTO измерены либо явно UNKNOWN |
| G5 synthetic deployment | Exact Git/image digest/Compose/secrets versions, one executor, no external business systems | Controlled stop/restart/fault/resource/access/restore acceptance, evidence T01–T14, owner final acceptance |

G2 можно подготовить в cloud до восстановления VPS, но текущее поручение
разрешает только infrastructure materials, не реализацию нового broker/MFA.
G1 и G2 независимы по разработке; G3 ждёт G1 и проверенную схему G2.
Не перепрыгивать G4 ради happy path; отсутствующая safety функция — blocker
соответствующих испытаний и полной приёмки.

## Before future changes checklist

- [ ] Provider console/support recovery работает с iPhone, независимый SSH key проверен.
- [ ] VPS действительно выделенный, нет CRM/неизвестных workloads; target точный.
- [ ] Read-only findings reviewed; cleanup чужих данных не авторизован.
- [ ] Конкретные bounded permissions/срок/cost/resources и rollback согласованы.
- [ ] Отдельные app/admin/runner/backup identities; no rootful socket у worker/API.
- [ ] Exact source revision + trusted build digest, contracts и CI согласованы.
- [ ] Secret provisioning безопасен; no values в чат/Git/логи/argv.
- [ ] VPN/HTTPS/MFA и independent emergency access работают; public API/DB/Redis закрыты.
- [ ] Rootless cgroups/quotas и orphan run enforcer проверены фактически.
- [ ] Offsite backup, restore key recovery, external anchors/watchdog подтверждены.

## Future acceptance matrix

| Check | Cloud сейчас | Требует VPS / внешней авторизации |
| --- | --- | --- |
| Template schema/negative security mutations | Offline tests + Compose config parse | Не подтверждает kernel/firewall/actual routing |
| Read-only helper | Fixture tests + local cloud files-only smoke | Реальная OS/нагрузка/packages/UID/network metadata |
| Launcher profile | JSON semantic checks и documented protocol | Реализация G2, rootless cgroup tests, host/daemon compromise boundary |
| Access | ACL/firewall/SSH текстовые templates | Real VPN identities, HTTPS trust/MFA/bypass tests, phone recovery |
| Backup/watchdog | Failure matrix/runbook consistency | Accounts/storage/alerts/immutability и полный DR drill |
| Existing F1 | Предыдущие 75 cloud tests из PR #10 сохранены | Целевые security/fault/resource/reboot/backup tests и owner acceptance |

## Rollback и остановка

До применения firewall/SSH проверить независимую console и сохранить scoped
предыдущую конфигурацию в защищённой custody. Не глобальный flush/restart.
После каждого изменения — вторая независимая сессия и конкретный smoke.
При отказе rollback только доказанно совместимой конфигурации; не выключать
MFA/firewall, не выдавать root AI. App rollback — exact prior artifact и schema
compatibility; необратимые DB migrations автоматически не откатываются.

## Что отдельно разрешает владелец

G1 SSH/доступ/read-only аудит; G2 новый launcher/auth code stage; G3 любые installs,
пользователи/сети/порты/SSH/firewall/VPN/DNS/certs/reboots/secrets; G4 аккаунты,
хранилища/alert services/новые расходы/restore operations; G5 развёртывание и
fault tests. Protected merge, production, реальные данные/AI/Telegram/CRM и
следующий этап не входят даже в synthetic trial автоматически.
