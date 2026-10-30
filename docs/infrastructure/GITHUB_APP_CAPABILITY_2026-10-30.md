# GitHub App: repository.push и отдельная проверка Git-сервиса

## Наблюдение владельца, 30 октября 2026

Действующий Commander остаётся на d932baaf; владелец отдельно собрал application
2822320569ca442ff5579140875ec074e1058898 на двух rootless daemons. Получен marker
FIRST_EXPERIMENT_AUTHORIZE_IMAGES_BUILT_NOT_DEPLOYED, coding image
sha256:2718bba964ce8aff054f41e35bbd2eb685b8076fd267de06924d74a3176025dc.
Это build evidence из SSH владельца, не применение обновления.

OpenAI UI: project AI Command Center, acc-first-experiment Active, List models/read,
Responses/write; ключ истекает5ноября2026 09:17:58UTC. Billing UI показывает$8.00
и auto-reload OFF. Это не генерация, не готовый финансовый профиль и не paid consent.

Первая legacy token attempt сохранена: нет local credential и точного stage.
Second attempt была absent, затем владелец отдельно разрешил ровно одну выдачу
по plan50654acd60e8a283211431989cb9c5ec8fdd976c5b7d4f3b8263601ac46f01b6,
operator8e605680d73e97365c29612c4d6d74c18bafd9c6. Все три App GET дали200,
выдача201; scoped enumeration/repo/main GET дали200. Effective count_is_one и
target_only true. Кандидат390bytes,UID1000,0600,regular,nlink1 сохранён, final
installation.token отсутствует. Фаза REQUIRES_INSPECTION_NO_RETRY, stage
repository_validation, error first_experiment_repository_preflight.

Все recorded_repository_checks true, кроме push_true:false. Включая точный
numeric ID/name, admin:false, active/unarchived repo, protected main и seed SHA.
Дополнительный owner-operated readonly GET к точному GitHub receive-pack
discovery endpoint дал200 и корректный advertisement prefix/content type/flush.
Токен не выпускался повторно, refs/files не менялись, candidate не продвигался.
Recorded expiry **2026-10-30T09:41:31Z = 12:41:31 МСК**. После этой даты
его нельзя использовать. Доступ и оставшийся срок перепроверяются при применении.

Эти сведения — owner-provided outputs, не прямой cloud SSH probe. Полного
pkt-line parser в том первоначальном ручном probe не было; он не является
runtime evidence новой реализации и не доказывает успешный push/REST write/PR.

## Исправление

Repository metadata permissions.push не является единственной проверкой
GitHub App capability. Стандартный validate_repository без дополнительного
evidence по-прежнему требует push:true. Только trusted operator/publisher,
получившие свежий ответ отдельного Git GET тем же credential, могут предоставить
его нормализованную projection. Не подменяется metadata.push и не принимаются
флаги из task/model/config/UI вместо сетевой проверки.

Общие проверки numeric ID/full_name, archived/disabled/admin:false, main name,
protected:true и exact seed SHA выполняются до дополнительного GET и после
него. При push:false/absent выполняется только:

`GET https://github.com/OWNER/acc-f2-synthetic-NAME.git/info/refs?service=git-receive-pack`

Никакого POST receive-pack, Git pack upload, git push или изменения refs. URL
фиксирован выбранным synthetic repo; нет произвольного host/path/query/body.
HTTP Basic x-access-token использует existing installation token только в trusted
process. Redirects запрещены, timeout/64KiB bound прежние. Полный pkt-line parser
проверяет service header, flushes, размеры, конечный offset, first-ref capabilities,
уникальность refs и присутствие main, максимум256refs. Projection содержит только
schema/repo/service/main_sha/refs_count/SHA256, без raw refs/capabilities или body.
Дополнительное evidence обязано совпадать с exact repository и BASE_SHA.

Runtime использует прежний Gateway.request: F1 authority, grant/config/source,
lease/fence/runtime guard, durable INTENT до I/O, ExternalAction/audit anchor,
UNCERTAIN no-repeat и проверки после I/O сохранены. Новый kind github_git
разрешает только этот GET внутри first-experiment profile. Отмена/неясный ответ
не допускают AI или публикацию. GitHub request IDs допускают bounded colon
separator; OpenAI ID contract прежний. Credentials всё ещё только у broker.

Оператор использует тот же parser. Неудача сохраняет candidate и redacted
stage/event; POST выдачи остаётся единственным. inspect --probe допускает этот
дополнительный GET при необходимости, но не пишет исходную квитанцию, не создаёт
final token, не снимает NO_RETRY и не выдаёт deployment/paid разрешений.
Успешное объявление Git-сервиса проверяет доступность discovery, не гарантирует
прохождение будущего branch rule или конкретной REST write operation.

Нужны новые exact-source images и новый named release, сохраняя все10 старых
pairs. Уже собранный2822320 не исправляется сменой label или файла на месте.
Старые candidate/receipt не копируются вручную в final credential. Последующие
credential reconciliation, owner decision, financial/runtime evidence, candidate
prepare/inspect/apply и первый paid consent остаются отдельными действиями.

## Проверки и источники

Локально150 PG/strict-mock cases passed /6 source execution cases deselected /
1 прежний Starlette warning; включает41 новых parser/gateway cases. Отдельно96
operator cases passed, включая7 новых. Новая app-token full container scenario
остаётся обязательной в fresh-source CI. Ранние исправленные fixture failures
не считаются положительным evidence. Final HEAD/полные counts — в Draft PR.

Официальные источники проверены30октября2026:

- [GitHub App permissions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app): installation auth зависит от App permissions, не прав пользователя.
- [Installation auth](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation): HTTP Git с installation token и Contents permission.
- [Git HTTP protocol](https://git-scm.com/docs/http-protocol): readonly ref discovery, pkt-line contract и отдельный POST для обновлений.

Mock tests и успешный CI не являются реальным paid/PR/rootless/phone acceptance.
