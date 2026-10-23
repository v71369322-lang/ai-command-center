# F1: границы безопасности и остаточные риски

Требования владельца имеют приоритет. Конкретные схемы, лимиты, tooling — DERIVED
implementation choices, не новые исторические approvals. См. H-F04/06/07/11/12/13/15,
H-I06/08/14/15/16/17/20. Реальные проекты не подключены; CRM автосервиса PAUSED.

- Roles: owner подтверждает/отзывает/останавливает; operator создаёт/смотрит и
  отменяет свои задачи; agent не имеет control-plane API полномочий.
- Идентичность проверяется сервером по отдельным synthetic bearer secrets.
  Нет default credentials, query-string tokens, localStorage или CORS allow-all.
- Approval привязано к task UUID, payload digest, версии, epoch и expiry;
  используется атомарно с claim. Повторный delivery не повторяет admission.
- PG lock/version/fence защищают admission и поздние callbacks. Не обещаем
  exactly-once эффекты или атомарность между PostgreSQL и Docker.
- DB outage блокирует старт/продолжение; lease expiry → RECONCILING.
  Реальный внешний API не может пользоваться предположением синтетического
  reconciler, что все эффекты находятся в disposable container.
- Executor: отдельный контейнер/run, non-root, network=none, read-only root,
  no capabilities, no-new-privileges, tmpfs, CPU/memory/PID/file/time limits.
  Нет Docker socket/SSH/host mounts/credentials. Только JSON → Markdown.
- 16 значений ограничивают полезные шаги фиксированного адаптера; произвольного
  AI-планировщика/счётчика его шагов здесь нет. JSON/Markdown не исполняются.
- Verifier находится вне executor, не доверяет self-report. Агент не меняет
  verifier/эталоны/policy. Значимые изменения требуют независимого review.
- API имеет ограничение тела 8 KiB, строгие схемы, CSP и безопасный React text
  rendering. Известные runtime secrets не принимаются в task content.
- Audit содержит цепочку digest; app DB role может SELECT/INSERT audit, но не
  UPDATE/DELETE. Полностью привилегированный DB/host admin может переписать её:
  без независимой ранее сохранённой контрольной точки этого не исключить.
- Ключи backup отсутствуют у executor/API; admin DB credential отсутствует в API.

## Нельзя объявлять закрытым

1. Worker/launcher имеет **полномочия Docker daemon облачного тестового хоста**.
   Они не передаются executor. Это доверенный операторский компонент, не
   ограниченный Docker proxy. На VPS необходим отдельный review его placement,
   прав и более узкого launch boundary. Не добавлять coding agent в docker group
   сервера автоматически. API контейнер socket не получает.
2. Конкретный VPS, firewall/VPN/HTTPS/MFA, соседние нагрузки и независимый
   аварийный путь не проверены. Loopback binding не заменяет эти проверки.
3. Внешняя защищённая custody backup/checkpoints, retention/immutability,
   key recovery и независимый watchdog ещё не подключены. Локальная копия
   **не является offsite**. Новые услуги/права не приобретаются автоматически.
4. Систематические adversarial tests, длительные resource испытания (короткие CPU/PID тесты уже выполнены),
   rate-limit/circuit-breaker hardening, полное independent security review и независимое
   review всего изменения не завершены. Это blockers приёмки, а не PASS.
5. Recovery interlock нельзя снять через обычный API. Процедура безопасного
   resumption после полного incident/restore требует дополнения и review;
   нельзя вручную снять halted/recovery ради прохождения теста.
6. DB volume/cloud-host disk не имеет проверенного отдельного host quota;
   audit/readiness ещё не содержит полноценного контроля host resource exhaustion.

При подозрении на нарушение границ: owner stop, запрет новых запусков, сохранение
PG/контейнерных evidence, ограниченный отзыв прав; не удалять журнал ради cleanup.
При недоступности Docker остановка не считается доказанной и включается halt.
Опасное возобновление требует точного разрешения владельца.
