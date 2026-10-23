# F1: backup, checkpoint и изолированное восстановление

Только синтетический контур. Никакого SSH/VPS/production restore в этом задании.

`command_center.recovery` использует реальный PostgreSQL `pg_dump -Fc`, AES-256-GCM
с новым nonce на архив, authenticated header. Ключ — отдельный файл, не Git,
не audit/task. Архив создаётся без overwrite. Restore создаёт только **новую**
БД `f1_restore_*`; имя `f1`/существующая БД отклоняется. Восстановление в другие
тома/инстанс потребуется для полноценного доказательства независимости.

Команды выполняются доверенным оператором с отдельными admin settings и ключом:

```sh
python -m command_center.recovery backup --file /authorized-custody/f1.enc --key-file /protected/backup-key
python -m command_center.recovery checkpoint --file /authorized-custody/f1-anchor.json
python -m command_center.recovery verify-checkpoint --file /authorized-custody/f1-anchor.json
python -m command_center.recovery restore --file /authorized-custody/f1.enc --key-file /protected/backup-key --target f1_restore_drill
```

Пути выше — placeholders разрешённого хранилища, НЕ уже созданное offsite storage.
Переменные DB/Redis/identity bindings те же, что у приложения; для restore
F1_DB_USER=f1_admin и отдельный admin password file. Не передавать пароль в argv.
`--container` по умолчанию только `acc-f1-db-1`; оператор обязан проверить target.

После восстановления: halted=true, recovery=true, новый epoch, все approvals
revoked, незавершённые задачи RECONCILING. SUCCEEDED/CANCELLED история сохраняется.
Даже старая копия не получает автоматическое право запуска. Сверить с независимой
контрольной точкой/последними отменами; отсутствие доказательства → оставлять блок.

Автотест проверяет: настоящий dump/restore, повреждение архива, старую копию до
последующей отмены, recovery interlock и сохранность исходной БД. Ключ теста —
явная fixture, не runtime credential. Время теста не является доказанным RTO:
не измерены полный disaster recovery, доставка offsite, доступ и key recovery.
RPO≤15min/RTO≤4h — provisional targets. WAL/PITR и расписание копий не реализованы
этим dump toolbox; actual external custody и restore drills — gates приёмки.
