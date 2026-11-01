# Единое обновление Telegram: resume и сводка готовности

Этот этап готовит доставку уже проверенных функций PR #37 и #39 за одно
обновление с последней подтверждённой VPS-версии. Приложение и архитектура здесь
не меняются. Выполнение на VPS, новые доступы и расходы не разрешаются этим
документом или успешным CI. Пока владелец вне компьютера, все действия — в облаке.

## Точные версии и зависимости

| Назначение | Закреплённое значение |
| --- | --- |
| Последний owner-provided live source | `b2e71fe073f3109e639dac43496884905ce86d9f` |
| Последний VERIFIED live bundle | `a1cf9b0d783cc15a17e8d119167008a81584a051bcd55a0e9b359c519d8be9c8` |
| Active bundle directory | `/home/acc-control/f34/candidate` |
| Data root | `/home/acc-control/f30/state` |
| Новый application target | `d932baafce53c0748396abfc019cf81b931ebfec` |
| Fixed release profile | `telegram-mobile` |
| Новый private workspace | `/home/acc-control/telegram-mobile-release` |
| Operator tools | Окончательный HEAD отдельного PR с этим документом |

Target application из [PR #39](https://github.com/v71369322-lang/ai-command-center/pull/39)
включает `/resume` с подтверждением, `/readiness`, меню и выбор проекта.
[Его CI](https://github.com/v71369322-lang/ai-command-center/actions/runs/40823146875)
успешен: **724 Python /1 warning**, отдельно **210 infrastructure**;
merge-ref `f3f15422450a106d17b5f571b14f0cb7741f1cee` связывает d932baa с f69f1fb.
Это проверочный Git ref, merge PR не выполнялся.

Цепочка: новый operator PR → #39 → #38 → #37 → #36 → #35 → предшественники,
включая исправленный deployment #17. `main` не назначается базой автоматически.
Старые `f34` и `telegram-resume` продолжают означать ровно прежние пары версий;
новый профиль не выбирается автоматически. `bdc8cbc` не требуется ставить отдельно.
Если source на сервере уже отличается от b2e71fe, этот маршрут останавливается.

Сравнение восьми exact Git blobs b2e71fe → d932baa подтверждает неизменность
models.py/admin.py, requirements.lock/uv.lock, Dockerfile/Dockerfile.executor,
compose.yaml и web/package-lock.json. Для этого перехода не нужна новая миграция
или установка пакетов. Это не отменяет проверки реальной БД и preflight перед apply.

## Подготовленный путь применения

1. При возвращении к серверу — свежая read-only сверка deployment.json, source,
   active directory и служб. Исторические F34 logs не заменяют текущую сверку.
2. Отдельное ограниченное разрешение на fetch/build/stage, затем получение clean
   operator checkout по точному финальному SHA через существующий read-only ACC
   deploy key. Приватные ключи и Telegram token остаются только на сервере.
3. Под acc-control использовать прежний `infra/vps/prepare_telegram_resume.sh` с
   явным `ACC_TELEGRAM_RELEASE=telegram-mobile`, точным `ACC_OPERATOR_REVISION`
   и новым абсолютным `ACC_PREPARE_APPROVED_UNTIL` (максимум 2 часа). Эти параметры
   передаёт оператор после согласования; дата сама не продлевается. Запуск без
   selector сохраняет старый `telegram-resume`, поэтому selector здесь обязателен.
4. Script проверяет UID1000/brain1, exact VERIFIED predecessor и 25GiB свободного
   места; новый workspace не перезаписывается. Использует прежние strict host-key
   checks, fixed private GitHub repository и rootless build_release.sh для обоих
   daemons. Получает только d932baa, делает disabled prepare, затем именованный
   live stage. Старые config, data и journal остаются действующими.
5. Успех подготовки: `TELEGRAM_MOBILE_CANDIDATE_PREPARED_NOT_APPLIED`. Получить
   **реальный** candidate bundle digest после host build/inspect. В облаке нет
   нового host image ID или готового host bundle digest; их нельзя подставлять.
6. Отдельно согласовать оба bundle digest и новый apply deadline (максимум 1 час).
   С точным operator tool, новым application PYTHONPATH и прежним tools-python
   использовать существующий apply interlock:

```text
stage_telegram_update.py apply --release telegram-mobile --active-bundle /home/acc-control/f34/candidate --output /home/acc-control/telegram-mobile-release/candidate --approved-previous a1cf9b0d783cc15a17e8d119167008a81584a051bcd55a0e9b359c519d8be9c8 --approved-candidate EXACT_HOST_CANDIDATE --approved-until EXACT_NEW_DEADLINE
```

Это описание будущего действия, не команда для запуска сейчас. Старые F33/F34
окна истекли; ни script, ни профиль не продлевают их. Будущий transient service
может удержать согласованный процесс при разрыве SSH, как в F34. Deadline клиентов
не объявляется гарантией прекращения уже принятой Docker BuildKit daemon работы.

## Приёмка с телефона после отдельного применения

1. Проверить activation/deployment VERIFIED, postcheck и exact application source.
   Приём задач автоматически не возобновляется.
2. `/readiness`: новая source d932baa, обычная остановка, сохранённая очередь.
   При отсутствии gateway config допустим именно UNKNOWN, а не подтверждение AI.
3. `/request 131179132` и `/request 131179125`: сохранены прежние тексты и назначения,
   если свежая сверка не обнаружила последующих правомерных изменений владельца.
4. `/resume` → одна свежая кнопка владельца → ответ о снятии обычной остановки.
   Recovery, безопасность или неизвестное исполнение остаются блокерами.
5. Один `/coding_demo`: failed checks → исправление → independent verifier →
   SUCCEEDED → Telegram result. AI и PR остаются mock; настоящая публикация не нужна.
6. `/stop`, затем `/readiness`: новые запуски закрыты. Старые отменённые задачи
   не перезапускаются. Приёмка реального AI/платёжных списаний этим не подтверждается.

Парольная web-панель остаётся loopback-only с прежним SSH tunnel. Публичный HTTPS,
VPN, новые credentials, реальные CRM, voice или paid API этим этапом не включаются.

## Отказы и сохранность данных

Все прежние stage/apply guards сохранены: exact source/image pinning, schema,
DB/Redis, UIDs, data root, owner login и bot/owner binding, VERIFIED predecessor,
deployment.lock, пауза poller, encrypted backup, update и postcheck. Apply требует
отдельных согласованных digests. Существующий activation journal блокирует retry.

При ошибке сохранять logs, directories, immutable images и оба журнала. Не удалять
marker, не делать blind retry, автоматический binding rollback или DB restore.
Сначала определить фактическую фазу. Предыдущие images/config/backup нужны для
проверяемого совместимого отката; их наличие не означает выполненный restore
или offsite backup. Эти правила — прежний [runbook доставки](TELEGRAM_RESUME_RELEASE.md).

## Что проверено в облаке

Локально **348 passed /1 прежний Starlette-httpx warning**:
infra/vps/tests + tests/test_deployment.py. **280 infrastructure** входят в348;
это пересекающиеся наборы, их не складывать. Та же stage/apply матрица проверяет
все три фиксированных профиля, включая ошибочный выбор другого профиля с тем же
predecessor. Проверки выполняются на private реальных файлах и Compose config,
с явно обозначенными fake engines/Deployment; production guards не подменены.

Проверены CLI stage/apply propagation, legacy defaults, wrong source/scope,
tampered binding, races, сроки, lock, output custody, partial output и no-retry
после неопределённости. Shell validation/selection prefix выполнен отдельно **до**
host guard без Git/Docker/host access; его точные target/path/marker сверены с
Python profile. Invalid/expired/overlong scope отказывает до host access.
Полный положительный shell build/stage/apply на brain1 здесь не выполнялся.

Ruff, OpenAPI, TypeScript/Vite и security/dependency gates PASS: 64 Python packages,
0 Python/npm advisories, 0 Bandit MED/HIGH, 84 reviewed LOW. Known-runtime-secret
guard не является универсальным сканером секретов. Src приложения, schema,
dependency locks, Dockerfiles и Compose этим operator PR не меняются.

Окончательный CI нового operator SHA фиксируется в PR. Его результат не заменяется
предыдущим application CI. Физический iPhone, rootless/systemd на VPS и доставка
пакета остаются отдельной приёмкой. Без нового разрешения к VPS не обращаемся.

## Восстанавливаемые cloud-артефакты

В ignored `.runtime/telegram-mobile-release/` подготовлены source archive и
manifest. Это source-only evidence, не готовый host bundle и не ссылка для
скачивания. Доставка использует private GitHub непосредственно с VPS; Windows,
GitHub Releases и передача images.tar не требуются.

Архив `source-d932baafce53.tar.gz`: **696076 bytes**, **317 entries**,
SHA-256 `26758aee9d731c6aee817a3868a15fe8b3eced6edcf1b6b072f50b82b23b0ddf`.
Встроенный Git commit ID проверен как d932baa. Два независимых git archive
в текущей среде дали одинаковые bytes; tar paths/link types проверены, .git,
.runtime, node_modules, .venv и runtime key/token files не включены.

В новой cloud-сессии source можно восстановить из GitHub по точному SHA:

```text
git archive --format=tar.gz --prefix=ai-command-center/ d932baafce53c0748396abfc019cf81b931ebfec --output=source-d932baafce53.tar.gz
```

Архив сохранять только в ignored/private workspace. Сверять embedded commit,
размер и SHA-256; несовпадение не скрывать переписыванием старого manifest.
Версии Git/compression могут влиять на bytes; проверенная точка исходников
остаётся заданным commit. Operator tools восстанавливаются по финальному SHA
этого PR. Manifest явно хранит отсутствие host image IDs, bundle digest,
выполнения на VPS и новых разрешений; после пересоздания cloud-сессии доступ
к серверу или разрешение deployment из него не выводятся.
