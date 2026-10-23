# Cloud F1 evidence

## Подтверждённый результат

Последний завершённый cloud run: **47 passed, 0 failed, 0 errors, 0 skipped**,
47.699 s; JUnit timestamp `2026-10-23T14:59:46.662005+00:00`.
Одна deprecation warning Starlette/httpx; это не failed test.
Прогон выполнен на рабочем дереве после исправления non-root Redis. Он не
выдаётся за финальный clean-tree CI конкретного итогового SHA.

Implementation: `d5463efcd97fbc22a24eb38dc73ec11e8919516c`.
Redis fix и дополнительные regression assertions:
`093f0cdccc56c309464ccbd7e67d1b11148429ec`.
Последующий финальный прогон был прерван; успешный container smoke для последнего
коммита **не подтверждён**. Файла `.runtime/container-smoke.json` нет.

Проверены реальные PostgreSQL/Redis, отдельные Docker executor runs, verifier,
Chromium 390px, отмена/timeout, CPU/PID/memory/file/tmpfs ограничения, lease/fencing,
подтверждения, аудит и отдельный pg_dump/pg_restore. Детали — tests/ и
[матрица T01–T14](ACCEPTANCE.md), которая сохраняет незакрытые полные группы.

Ruff, TypeScript/Vite build, contract drift check и проверка tracked files на
текущие runtime credentials проходили. npm audit: 0 известных advisories;
pip-audit: 25 runtime dependencies, 0 известных advisories. Это snapshot баз
advisories, не гарантия отсутствия уязвимостей; dev Python dependencies не входят
в этот pip-audit snapshot.

## Что ещё выполнить в этой ветке

1. Собрать оба образа с `F1_SOURCE_REVISION=$(git rev-parse HEAD)`.
2. Повторить scripts/cloud_test.sh на clean tree, включая новые Redis assertions.
3. Проверить Compose API image + отдельный worker + static web как один запуск.
4. Приложить trusted CI outcome и независимое review; обновить этот evidence.
5. Не закрывать внешние custody/VPN/MFA/VPS gates по локальному успеху.

SSH/VPS/реальные API/клиентские данные/платные ресурсы/merge не использовались.
Полная приёмка F1 и owner acceptance отсутствуют.
