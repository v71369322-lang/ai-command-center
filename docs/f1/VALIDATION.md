# Cloud F1 evidence

Проверенный clean-tree код: `31d3f89aef1b887bc2567ec7a86d0708041df68d`.
Команда: `F1_BUILD_CA_FILE=/etc/ssl/certs/ca-certificates.crt scripts/verify_cloud.sh`
с установленным Chromium в разрешённой cloud-среде.

- **60 passed**, 0 failed/errors/skipped, **66.33 s**.
- Одна Starlette/httpx deprecation warning, не скрыта.
- Ruff, OpenAPI drift check, TypeScript/Vite, locked container builds: PASS.
- Compose API + worker + PostgreSQL + Redis + Outbox + approval + изолированный
  executor + независимый verifier + web: PASS.
- Restart API/worker: сохранённый результат, отменённая задача без запуска,
  выполнение новой задачи после перезапуска: PASS.
- Runtime inspect: non-root, read-only rootfs, capability drop, loopback API,
  API без Docker socket, worker без owner identities: PASS.
- Зашифрованный backup → отдельный PostgreSQL container с network=none →
  recovery interlock и audit verification: PASS, **6.788 s**.
  Это не offsite drill и не доказательство RPO/RTO.
- pip-audit: **62 runtime/dev dependencies, 0 advisories**; npm audit: **0**.
- Bandit: **0 MEDIUM/HIGH**, 16 разобранных LOW; причины в
  [SECURITY_REVIEW.md](SECURITY_REVIEW.md). Snapshot advisories не гарантирует
  отсутствия уязвимостей.

Образы: immutable IDs, OCI revision совпадает с проверенным SHA.

| Компонент | Image ID |
| --- | --- |
| API | `sha256:ec52db3d1cbfc96fa5e07fa6d94d265856da95735e8a1a5daecd83007e379f15` |
| Worker | `sha256:5b8dfd9f490695b1226885f7a5631e45c79a17ed88d8c30279f61deedcd4b392` |
| Executor | `sha256:eb6f15fdddb8f84d102fca690b535ad2e7c74c5a1b1ccb726dac0755f46ee4f4` |

JSON/JUnit/логи хранятся в ignored `.runtime/`; ключи, архивы и credentials
не публикуются. Повторный запуск создаёт свои доказательства. GitHub Actions
использует тот же профиль; его итог проверяется отдельно в
[PR №8](https://github.com/v71369322-lang/ai-command-center/pull/8).
Документационный коммит после указанного SHA не выдаётся за локально
повторно протестированный код.

[T01–T14](ACCEPTANCE.md) разделяет cloud-профиль и полную приёмку.
Независимое review кода, защищённая независимая custody checkpoint/offsite backup,
key recovery, watchdog, VPN/HTTPS/MFA, VPS audit/quotas не подтверждены.
Trusted launcher имеет локальный Docker socket: это не доказательство
безопасного размещения на общем VPS. RPO/RTO остаются предварительными целями.

SSH/VPS, реальные API/данные, новые платные ресурсы и merge не использовались.
F1 не объявляется принятым владельцем или полным MVP.
