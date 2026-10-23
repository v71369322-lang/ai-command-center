# Проверки инфраструктурного пакета

## Выполнено в cloud, не на VPS

- 32 offline tests, 0 failures, 0.08 s. Negative mutations: public IPv4/IPv6
  ports, socket/host mounts в API, privileged/host network/PID/devices/caps,
  root user, missing/oversized limits, unbounded tmpfs/logs, latest image,
  external volume/network и include/entrypoint overrides, worker/admin secret.
- Read-only probe fixture/timeout/argument checks: нет remote/apply interface,
  files-only не запускает команд и не публикует неизвестные поля/секреты.
- Rootless launcher design/ACL/firewall placeholder checks; это не runtime tests.
- Ruff `infra/vps`, `git diff --check`: PASS.
- `validate.py compose.control-plane.json`: PASS_TEMPLATE_ONLY, deployable=false.
- `--require-deployable`: ожидаемый отказ code2, gate сохранён.
- Docker Compose `config --quiet` с публичным fake image digest и source fixture:
  PASS. Это только parser, никаких pulls/up/remote connections.
- Probe `--files-only` выполнен на текущей cloud-среде, readiness=UNVERIFIED.
  Он не описывает VPS и не загружен в Git как серверный отчёт.

Команды — [infra/vps/README.md](../../infra/vps/README.md). Новая CI job выполняет
offline tests/lint/template/probe; прежний F1 workflow не изменён. Actual remote
CI outcome публикуется в PR отдельно, не утверждается по наличию workflow.

## Не выполнено и не разрешено

SSH/TCP probe/port scan/remote commands; OS/package/security findings VPS;
install/update/rootless cgroups; применение firewall/VPN/SSH templates; создание
accounts/domains/certificates/paid storage; runtime shim/enforcer implementation;
external alerts/backup/anchor custody; реальный reboot/restore/DR/phone-loss drill.
Никакая непроверенная функция не считается работающей. F1 acceptance не закрыта.

Нужна независимая проверка правил на реальном Docker backend/IPv6 и rootless
UID mapping. Validator не универсальный security proof и не заменяет host audit.
Пакет не изменяет src/web/старый Compose/requirements lock/исторические R/D/H.
Все серверные operational status сведения остаются owner-reported.
