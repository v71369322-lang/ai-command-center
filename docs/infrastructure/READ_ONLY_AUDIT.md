# Будущий read-only аудит: без запуска сейчас

План не выполнялся на VPS. Начальные условия: отдельное разрешение на конкретный
IP/учётную запись/срок; защищённый credential через штатный канал; независимый
SSH host-key fingerprint из provider console/support, не из той же SSH-сессии.
ssh-keyscan/первый TOFU не независимая проверка. Панель сейчас не подтверждена
работоспособной; без console recovery hardening/deploy gate закрыт.

Облачный Codex должен иметь официально разрешённый маршрут/доступ только к новому
VPS. VPN iPhone не предоставляет cloud-среде этот доступ автоматически. Ни ПК,
ни PowerShell/WSL, ни CRM jump host не нужны и не допускаются.

## Последовательность проверки

| Шаг | Read-only evidence | Stop/UNKNOWN |
| --- | --- | --- |
| 1 identity | Independent fingerprint, точный IP, пользователь, scope | Не совпал key/сервер → не входить |
| 2 OS/packages | /etc/os-release, kernel, package versions, dpkg --audit, существующий cache updates | apt update/upgrade запрещены в read-only; cache может быть stale |
| 3 resources | CPU/vCPU, MemAvailable/swap, df free/inodes, load, cgroup v2/controllers, quotas | Это snapshot, не benchmark/проверка производительности NVMe |
| 4 network | Локальные интерфейсы/routes/listeners, IPv4+IPv6, nft/iptables rules в scoped privileged read | Не выполнять сканирование внешних адресов, speedtest или публичный port scan |
| 5 SSH | Trusted admin sshd -T/-C, includes/Match/cloud-init, ключевой auth, root/password policy | Не читать private keys, authorized_keys целиком или дампы credentials |
| 6 services | Service names/status, Docker version/security options/rootless, container names/state/ports/limits только synthetic scope | Не docker inspect full Config.Env, не logs/exec чужих workloads, не restart |
| 7 boundaries | Socket owners/modes, sudo/groups metadata, AppArmor/seccomp/userns, cgroup delegation, no host TCP daemon | Не расширять group/sudo; rootless limits без фактической проверки UNKNOWN |
| 8 storage/security | Volume/layout/permissions metadata, log rotation/journal limits, backup destinations metadata | Не открывать клиентские БД/логи/backup contents и secret files |
| 9 emergency | Provider recovery доступен с iPhone, второй путь MFA/recovery, план reboot/stop | Не перезагружать ради проверки в read-only |
| 10 conclusion | PASS/FAIL/UNKNOWN по каждому gate, exact evidence/time/source | Неизвестное не считать безопасным; чужие workloads → остановить подготовку размещения |

## Локальный helper

`python infra/vps/read_only_probe.py --files-only` читает только allowlisted local
OS/proc/cgroup metadata. Без флага добавляет fixed `uname`, `dpkg-query`,
`dpkg --audit`, `ss -lntu`, `systemctl is-active`; никаких SSH/network probes,
sudo/install/update/restart/config writes. Вывод listeners — protocol/port без
process argv/адресов. UNKNOWN/missing tools не означает failed host или ready host.
Скрипт не принимает --host/--remote/--apply и не запускает произвольные команды.
Факт локального cloud smoke не описывает VPS.

Перед запуском на VPS проверить exact Git/file checksum; передавать helper только
в рамках отдельно разрешённого действия (даже upload файла — изменение сервера).
Для строго read-only этапа использовать одобренный execution channel без upload,
например передать проверенный текст interpreter stdin через защищённую сессию.
Автоматического SSH harness здесь нет. Вывод хранить в restricted evidence,
не публиковать необработанные interface/account/security данные в PR.

Расширенные privileged read checks выполняет только администратор в разрешённой
облачной сессии. Не запускать sudo интерактивно наугад и не выдавать агенту root
ради полноты отчёта. Сначала завершить доступные checks, недоступные пометить OPEN.

## Отдельный будущий изменяющий этап

Патчи ОС, установка Docker/rootless UID/cgroup, firewall/VPN/SSH конфигурация,
secret provisioning, сети/тома, резервирование, service units и reboot требуют
нового bounded authorization. Сначала console rollback + независимый доступ,
затем по одному изменению с проверкой второй сессией, без блокировки владельца.
Шаблоны в infra/vps/templates не являются разрешением на применение.
