# F34: подготовка обновления действующего Telegram

База operator tooling — Draft PR #35, `b2e71fe073f3109e639dac43496884905ce86d9f`.
Это также точный target application SHA; инструменты этого PR находятся в infra,
а не в приложении. Main и цепочка зависимостей не объединяются.

## Что подтверждено

Работающее приложение: `316dc1615dea224bcf4bd595d87048d19820bd21`, bundle
`0ee8a6023296fdacfe632c2f364c488b2564db399bfd15af357812e41004d64b`.
[Подписанные проверки F33](https://github.com/v71369322-lang/ai-command-center/blob/c4aa5a8449ba1e9a57d3922160bae3ffb33ced70/docs/infrastructure/F33_LIVE_VALIDATION_2026-10-28.md)
подтвердили настоящий GitHub → VPS status, exact replay и отказ вне каталога.
Профиль ограничен 22:24:55 МСК 28 октября, max_updates=0; он не разрешает
сборку или это обновление и не продлевается автоматически.

PR #35 открыт Draft, HEAD совпал с target; полный CI
[40739927714](https://github.com/v71369322-lang/ai-command-center/actions/runs/40739927714)
SUCCESS. Его 651 Python / отдельно 105 infrastructure — предыдущая проверка
приложения, а не результаты новых инструментов или развёртывания.

models.py, admin.py, requirements.lock, uv.lock, Dockerfiles, compose.yaml и
web/package-lock.json между live и target не изменились. Новой DDL-миграции
для этого target нет. Сборка должна создать новые immutable image IDs с
label target SHA на обоих прежних rootless daemons; старые IDs не подменяются.

## Исправленный дефект подготовки

Live connection.json содержит source_revision прежнего приложения. Простой
prepare новой live-версии отвергается проверкой exact connection. Замена
этого файла до согласованного update остановила бы текущий клиент.

`infra/vps/stage_telegram_update.py stage` принимает отдельно подготовленный
обычным Deployment disabled bundle и действующий live bundle. Он проверяет
source, image IDs/labels на двух rootless daemons, VERIFIED predecessor,
идентичность схемы/DB/Redis/UID/data-root/login и прежний Telegram scope.
Создаёт только новый private candidate directory с bundle.json, compose.json,
connection.candidate.json и preparation.json. Ключ/токен не читает; текущие
connection.json, deployment.json и службы не меняет. Profile rendering и
последующий production binding guard сохраняются. STAGED_NOT_ACTIVATED
не означает разрешённый update: текущий live config по-прежнему отвергает target.

`apply` — отдельная локальная операция acc-control после нового явного
разрешения двух точных bundle digests и срока не более часа. Под существующим
deployment.lock повторно проверяет baseline, прежний preflight, target source/
images, binding и срок. Сохраняет private прежний config и durable activation
journal, подтверждает остановку старого poller и атомарно меняет только revision
конфигурации. Затем вызывает прежний Deployment.apply(update, exact_digest,
expected_previous=exact_digest): quiesce, encrypted backup, immutable compose,
postcheck и запрет автоматического resume остаются в существующем updater.
Внешние AI/CRM grants и GitHub publisher не добавляются.

Любая попытка apply оставляет activation.json. Даже если deployment.json ещё
VERIFIED на старом пакете, DEPLOYMENT_ATTEMPTED не означает отсутствие эффекта.
Повтор, autoretry, автоматический откат binding и сброс журнала запрещены.
Неопределённость требует чтения обоих журналов и фактических служб; старая
конфигурация сохранена для отдельно согласованного восстановления. Откат
приложения и возврат binding требуют совместного плана — обычный rollback
со старой конфигурацией не выдаётся за уже проверенный live rollback.

## Прямая доставка исходников: одно ограниченное подключение

Изолированный runner не может писать исходники в /home/acc-control и не должен
получать такие права неявно. F33 mailbox не используется для обхода этого запрета.
Нужен отдельный **read-only deploy key только этого репозитория** для trusted
acc-control. Windows-ключ, PAT, пароль владельца и token Telegram не используются.

Подготовлен `infra/vps/create_f34_source_key.sh`: после отдельного разрешения
создаёт новую private SSH-пару на VPS, не перезаписывает существующие файлы,
ничего не подключает и выводит только public key/fingerprint. Начальное окно
задаётся ACC_SOURCE_KEY_APPROVED_UNTIL, max один час; сам deploy key действует
до отзыва в GitHub и не является runtime permission обновления.

Владелец добавляет public key в Repository Settings → Deploy keys → Add deploy key,
**Allow write access выключен**. Нельзя использовать тот же key в других проектах.
Отзыв: удалить именно этот deploy key из GitHub; private key остаётся только
в /home/acc-control/f34-source-access, вне build context, mounts и runner.

GitHub host key сверён HTTPS GET https://api.github.com/meta 28 октября 2026:
ED25519 SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU.
Bootstrap сохраняет только соответствующий публичный known_hosts entry.
Это ключ GitHub, не подтверждение host key VPS. Будущий git fetch использует
BatchMode=yes, IdentitiesOnly=yes, StrictHostKeyChecking=yes и отдельный
UserKnownHostsFile; неизвестные ключи автоматически не принимаются.

## Порядок после подключения read-only ключа

1. Отдельно разрешить загрузку/сборку pinned source и operator helpers. На VPS
   проверить минимум 25 GiB свободного места и необходимые git/Python/Compose;
   ничего не устанавливать автоматически. Получить application checkout target
   SHA и отдельный checkout exact helper commit. Оба clean, без секретов.
2. Под acc-control выполнить существующий infra/vps/build_release.sh с
   ACC_CONTROL_UID=1000, ACC_EXECUTION_UID=1001. Нельзя менять daemons или source
   labels ради PASS. Старые образы/контейнеры остаются доступны по immutable IDs.
3. На tools Python существующего f30 и PYTHONPATH pinned target/src вызвать
   deployment prepare в **новом** disabled-bundle каталоге, прежний data_root
   /home/acc-control/f30/state, password origin http://127.0.0.1:18000,
   --password-loopback-http, без --telegram-connection-digest.
4. Вызвать новый stage с active bundle /home/acc-control/f32/bundle-telegram,
   disabled bundle, новым private output и --approved-previous live digest выше.
   Зафиксировать полученный candidate digest и реальные image IDs. При ошибке
   или response loss не повторять поверх существующего каталога.
5. Представить владельцу exact candidate/predecessor/source, backup/stop/downtime
   и recovery plan. Только после отдельного разрешения вызвать apply с этими
   двумя digests и --approved-until. Нынешний диагностический grant не расширять.
6. Проверить VERIFIED/postcheck, Telegram меню, сохранение нового текста,
   выбор проекта/устаревшую карточку, чтение прежнего запроса и синтетический
   тест. Голос, настоящие AI, CRM и paid calls остаются выключенными.

Шаблон вызовов (это не инструкция запуска без source/bundle approvals):

```text
tools-python stage_telegram_update.py stage --active-bundle ACTIVE --disabled-bundle DISABLED --output NEW_PRIVATE_DIRECTORY --approved-previous LIVE_DIGEST
tools-python stage_telegram_update.py apply --active-bundle ACTIVE --output NEW_PRIVATE_DIRECTORY --approved-previous LIVE_DIGEST --approved-candidate CANDIDATE_DIGEST --approved-until APPROVED_UNIX_TIME
```

## Практические проверки и ограничения

Локально 38 новых проверок: staging не меняет live state/binding и не читает
token; profile rendering совпадает с normalized Compose; wrong source/scope/
schema/login/owner/token-ref/mock mode, stale predecessor/race, path/symlink,
partial writes, expired/missing/wrong digest approvals, lock contention,
pause/apply uncertainty и запрет повторов. Fixtures используют реальные private
файлы и Docker Compose config **без обращения к daemon**; image/preflight/apply
backends здесь fake. Это не rootless/systemd/VPS acceptance.

Локальный общий запуск infra/vps/tests + tests/test_deployment.py: **211 passed,
1 прежний Starlette/httpx warning**. 38 входят в 211, не прибавляются.
Ruff/OpenAPI/TypeScript/Vite PASS. Ошибка первого тестового запуска была в
fixture live-profile re-render, исправлена без ослабления production validation;
негативные тесты теперь проверяют конкретный код отказа.

Bandit нового operator helper: две LOW B105 — фиксированный путь
/run/telegram/token, не token value. Находки сохранены, reviewed в
[SECURITY_REVIEW.md](../f1/SECURITY_REVIEW.md); suppressions и расширения
списка разрешённых правил не добавлялись.

Итоговые SHA/полный CI новых инструментов фиксируются в отдельном Draft PR.
На VPS новые ключи/исходники/образы ещё не создавались; GitHub Deploy key не
добавлен, app update не выполнен. Нет гарантии GitHub SSH egress с VPS, live
binding update/recovery и iPhone UX до отдельных разрешённых host-проверок.
