# F1 implementation contract

Требования — текущий разрешённый облачный F1 и ранее подготовленное ТЗ с T01–T14;
историческая база PR #7/R/D/H сохраняется. Конкретизация ниже DERIVED, не новые H.
Программирование сейчас разрешено только в облаке; размещение на VPS не разрешено.

## Инварианты

1. PostgreSQL — authoritative state, Redis — at-least-once transport.
2. Task UUID — stable operation ID; attempts/fence растут, old fence не закрывает run.
3. Task+intent+audit+Outbox атомарны. Publish-before-mark допускает delivery duplicates.
4. Lease/approval/revocation/epoch/current state перепроверяются до Docker launch и
   во время ожидания. Cancel/stop не обещают отменить уже совершённый эффект.
5. SUCCEEDED требует независимо проверенный manifest+result, не agent self-report.
6. Протокол executor только stdin JSON → stdout JSON manifest; реальных провайдеров нет.
7. Результат хранится в PG; disposable JSON/Markdown workspace удаляется после evidence.
8. Unknown action/identity/version запрещены. Approval одноразово для точного digest.
9. Отмена не возобновляется при recovery. Restore включает interlock и смену epoch.
10. Журнал hash-linked, но доверие при host compromise требует независимого anchor.
11. Backup encrypted вне runtime прав; offsite custody не имитируется локальным файлом.
12. Синтетические расходы не реальные деньги; hard ceiling/new commitment rules сохраняются.
13. Docker launcher trusted, executor untrusted; authority launcher — явный gate VPS review.
14. Critical failures или непроверенные обязательные gates блокируют полную приёмку.

## Контракты

[OpenAPI](../../contracts/openapi.json) version 0.1.0; `scripts/export_contract.py --check`
блокирует незарегистрированный drift. HTTP Authorization: Bearer synthetic secret.
Роли серверные, не поле команды. Команда: strict kind render/approved_render,
1–16 single-line bounded values, synthetic integer cost, optional task dependency.
Idempotency-Key обязателен, scope role+key, конфликт payload отклонён.

Queue v1: event_id + task_id; payload из Redis не используется как task authority.
Manifest: operation_id + integer fence + markdown; размер ≤64 KiB, exact expected
content, SHA-256. No arbitrary filenames/commands/shell/provider URLs.

Approvals: version+TTL input; server binds payload digest, operation ID, epoch,
expiry, usage and revocation. Resume normal stop: owner + exact epoch/journal digest.
Recovery/isolation resumption не делегируется этому endpoint.

Обычный grant этапа разработки не является runtime Approval. В рамках текущего
scope branches/tests/fixes/commits/PR автономны, но merge/access expansion/paid/
real integrations/следующий этап требуют отдельных полномочий.
