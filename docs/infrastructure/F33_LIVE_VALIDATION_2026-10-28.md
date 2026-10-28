# F33 — первый ограниченный канал на VPS: 28 октября 2026

Это протокол диагностического профиля, а не разрешение deployment или production acceptance.

## Зафиксированный scope

- Host brain1, отдельный runner acc-vps-operations, label acc-ops-mailbox.
- Immutable operator source: `eec068fa4a3558033e36cb572d3f9b6c081758fc`.
- Bootstrap source SHA-256 `527499daa7995c317783089b6e93e11103a7b33b81595085300e68e042e5d488`; после трёх проверенных исправлений PATH/prlimit — `5aa92cb60a3ac4a79a0d9a8e9c22b85e0c86652221b9b0ba1bc0a3e974a5bd3e`.
- Catalog `2309a2f9fc90609253228d7cf8d052f0f5c81a0a685a6a349656dd7c177f3a6a`: один действующий пакет, 3600 секунд, максимум 32 операции, max_updates=0.
- Policy `fcab87067bc7486179b49d889e67bd3a0bcb3ee07a7c70e8abb26fdcd928e534`, expires_at=1793215495 (28 октября 22:24:55 МСК).
- Public receipt key `DRyCPa1vwsughFY9Tz433RKnLgL2k/Ns3N4jwTRG3S8=`. Это публичный ключ проверки, не secret.
- Работающее приложение: `316dc1615dea224bcf4bd595d87048d19820bd21`, bundle `0ee8a6023296fdacfe632c2f364c488b2564db399bfd15af357812e41004d64b`.

## Подтверждённые результаты

1. Владелец через свой SSH подтвердил установку и регистрацию; mount active/mounted, timer active/waiting, runner active/running, operator Result=success / ExecMainStatus=0.
2. [Первый GitHub → VPS status](https://github.com/v71369322-lang/ai-command-center/actions/runs/40746141444), commit `35b07de2530ab591cb12ddbd5fd70856f3e24405`, job `123020413812`: GitHub SUCCESS, runner version 2.338.2 / machine brain1, repository token contents:read / persist-credentials:false.
3. Operation `e89370ed-7afb-4b89-b326-451f75456e36`: signed SUCCEEDED / verified, request_hash `9c267498d34f0525ed4a9abd1ea11a158dcacf8cd843a9f17732f500d596b109`, updated_at=1793212580. Подпись и привязка всех полей повторно проверены в облаке системным OpenSSL и проверенным submit.py.
4. Первый вызов занял около 3 минут 8 секунд от запуска producer до возврата квитанции. Журнал владельца показал processed=1, затем processed=0; причина длительности не установлена. Повторной операции не создавали.

## Последующие проверки этого же профиля

- [Exact replay — SUCCESS](https://github.com/v71369322-lang/ai-command-center/actions/runs/40747217444), commit `feafb96a13d8b2ffca9f1fb0ff921bd68da65462`, job `123024167424`: тот же operation ID и полностью неизменный payload. Receipt, signature и updated_at идентичны первому результату; Ed25519 повторно проверен в облаке. Producer прочитал существующую квитанцию без публикации нового intent; повторного backend status не было.
- [Негативный status](https://github.com/v71369322-lang/ai-command-center/actions/runs/40747402356), commit `4de2307163003fd8228590b9df0db803e3dbe8ed`, job `123024814623`: operation `def8806d-1b88-48f3-9ca3-7768a9feab52`, target=expected=64 символа f. Получен подписанный **REJECTED / bundle_not_approved**, request_hash `782321c305e2467c357fdae8bea8b4f71440248bde36b04e9057308278563a0f`. Ed25519 и request binding подтверждены в облаке; по закреплённому operator source отказ предшествует backend.prepare/execute. Workflow conclusion=failure ожидаем: неизменённый producer завершился exit 1 для REJECTED. Hosted validate и checkout прошли; причина mailbox failure подтверждена квитанцией. Continue-on-error и ослабление проверок не добавлялись.

## Границы результата

Прямого SSH из Codex нет. Первоначальные root-команды выполнил владелец в своём SSH; затем настоящий job на VPS и подписанный status проверены через GitHub. Автоматическая доставка новых исходников/сборок, update, rollback, reboot, offsite backup и отсутствие ручного SSH для любых будущих операций этим не подтверждены. Runtime grant ограничен сроком и не продлевается автоматически; автозапуск после reboot не включался.

Новые Telegram меню/выбор проекта и другие cloud PR этим не установлены. Платные AI API, CRM, реальные GitHub publisher credentials и публичный административный доступ не включались. Private signing key, runner credentials, пароль владельца и токен Telegram не читались облаком и не публиковались.

GitHub job сохранил предупреждение Node.js 20 action metadata: pinned checkout выполнялся на Node.js 24. Это предупреждение не скрыто.

## Сохранённые доказательства и оставшиеся проверки

[Публичные evidence JSON](evidence/f33-2026-10-28) содержат исходные submission и подписанные envelope для всех трёх job. Проверяются функцией verify в infra/vps/operations/submit.py и системным OpenSSL. SHA-256 producer из закреплённого source: `916598d5d9040e2ba22ff0b2180480d6fca91ec6684cf18ab60d9497d870fb49`. В облаке дополнительно подтверждён отказ при подмене receipt.state, receipt.code и policy/request binding.

Три mailbox job, два уникальных operation ID, ноль application updates. Это не новый полный Python/infrastructure suite. После проверки pending_request.json возвращён к исходному, уже завершённому status: сохранение payload для idempotency, не новый запрос. Коммит протокола без request marker запускает только hosted validate; mailbox skipped и не подменяет ожидаемо красный негативный workflow.

На настоящем VPS в этом этапе не проверены reboot/autostart, crash/recovery, конкурентное исчерпание квот, отдельные попытки доступа job к Docker sockets/secrets, update приложения и автоматическая остановка runner по expiry. Runtime policy проверяется при admission; её истечение не означает остановку systemd/runner процесса. Службы запущены через start, не enable. Постоянные полномочия не выданы.
