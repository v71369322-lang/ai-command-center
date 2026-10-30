# Подготовка GitHub credential для первого эксперимента

Продолжение [PR #46](https://github.com/v71369322-lang/ai-command-center/pull/46).
Это операторский инструмент, не новый runtime adapter или механизм grants.
Разработка и mock tests выполнены в облаке; настоящий App key остаётся на VPS.
В cloud-разработке live App запросы не выполнялись. Первая owner-operated
попытка30октября2026 описана ниже; её каталог нельзя использовать повторно.

## Наблюдение владельца 30 октября 2026

Владелец сверил VPS: прежний deployment VERIFIED на d932baaf, bundle fcab8e82…,
private key files UID1000/0600, private parents0700 и69GiB свободно. Подготовлен
operator0476b4c, offline plan a20ec688… с публичным SPKI SHA-256
3a3a41b6d4436f4f680f6e37c72f357d79fa86357b43d87fd3aab26e4a30a750,
совпадающим с прежним owner fingerprint. Затем выполнена локальная сборка
application a5d867c с FIRST_EXPERIMENT_IMAGES_BUILT_NOT_DEPLOYED.

Владелец выполнил одну выдачу по этому плану. Generic CLI вернул BLOCKED.
Read-only inspection в03:09:06UTC показал private receipt857bytes,
REQUIRES_INSPECTION_NO_RETRY, token_request_attempted=true и
expires_at=2026-10-30T04:06:33+00:00 (07:06:33МСК). installation.token и pending
receipt отсутствуют; application_configuration_changed=false, paid_calls=0.

По control flow0476b4c наличие expires_at означает, что POST вернул ответ и
первичный token metadata/scope check прошёл. Последующий этап отказал до
сохранения credential. Этот старый инструмент не записал ни точный stage, ни
ошибку и не удержал credential. Причину нельзя восстановить из этой квитанции;
legacy inspection не придумывает её. Значение токена отсутствует, но это не
отзыв upstream доступа. Исходная попытка остаётся неизменной, без удаления,
повтора или автоматического выпуска замены.

Отдельные read-only GET через Codex connection подтвердили ID1438229730,
main=a41d5fdf083fa0a162299b74ac9c155b58b140cb и protected=true. Это другая
identity, не проверка потерянного runtime токена. Защита permissions/baseline
в runtime не изменена. Здесь только owner-provided SSH evidence и отдельные
GitHub metadata reads; не прямой cloud SSH или новое deployment evidence.

## Закрываемый пробел

Владелец уже проверил App5524444, installation176497504, selected selection,
permissions и связь с тестовым репозиторием. App PEM нельзя монтировать вместо
короткоживущего installation token: runtime принимает другой credential и
ограничивает его размер. Этот этап готовит инструмент получения такого токена.

Scope фиксирован в коде: `v71369322-lang/acc-f2-synthetic-first`, ID1438229730,
App `acc-first-v71369322`, account ID346751364. Только Contents/write,
Pull requests/write, Metadata/read. Нет CLI-параметров смены аккаунта, repository,
endpoint или расширения прав. Не создаются ветки/коммиты/PR, не запускается AI.

## Будущее применение владельцем

Следующие команды описывают separately authorized операцию после reconciliation.
Первоначальный first-token-attempt уже занят: новую выдачу нельзя запускать
переименованием старого каталога или слепым повтором. Новый attempt/source/plan
и дополнительная выдача требуют нового конкретного решения владельца.
Операторский checkout нужно закрепить полным SHA из итогового Draft PR.
Application target `a5d867cb734a4954926a4e77c71e6f5be217057c` и восемь прежних
release profiles этим этапом не меняются. Новый runtime bundle здесь не создаётся.

1. После нового owner SSH reconciliation запустить от `acc-control` в чистом
   exact operator checkout offline `plan`:

   ```text
   .venv/bin/python infra/vps/prepare_github_token.py plan
     --key-file /home/acc-control/github-app-access/app-private-key.pem
     --output-directory NEW_CANONICAL_PRIVATE_ATTEMPT_PATH
     --operator-revision EXACT_OPERATOR_SHA
   ```

   Здесь переносы строк — отображение аргументов; практическая команда формируется
   одним блоком после reconciliation. Plan не создаёт HTTP client, каталог или
   credential. Он читает выбранный private PEM локально, выводит публичный SPKI
   SHA-256 и digest плана, связывающий key path/key identity/output path/source/scope.
   Значение PEM, JWT и пути в отчёт не выводятся. UID root отвергается.

2. Проверить план и получить конкретное разрешение владельца на эту выдачу с
   новым сроком до10мин. Только затем `prepare` с теми же аргументами и:

   ```text
   --approved-plan REVIEWED_PLAN_DIGEST --approved-until UNIX_DEADLINE
   ```

   Это не постоянный grant, автоматическое продление или подтверждение расходов.
   CLI flags фиксируют разрешение оператора; они не заменяют внешнее решение владельца.

3. Успех — `TOKEN_STORED_NOT_CONNECTED`. В новом private0700 каталоге находятся
   `candidate.token`, `installation.token` и redacted `receipt.json`, owner UID/0600. Не открывать
   значение токена в чат/browser/Git/logs. PEM остаётся вне контейнеров.

4. Получать токен непосредственно перед approved deployment preparation, чтобы
   не расходовать срок на ожидание. Файл передаётся прежнему явному deployment
   binding `--github-token-file`, только в trusted broker readonly. Config evidence
   о GitHub не должно жить дольше `expires_at`; старые receipts не подтверждают
   текущую доступность. Сам инструмент config/bundle/grants/ledger не меняет.

## Что проверяется

JWT RS256 существует только в памяти, с App ID issuer, iat на60сек назад и exp
через5мин. Три signed GET проверяют App identity/permissions, account, installation,
selected selection, отсутствие suspension и repository installation binding.
Затем один POST запрашивает `repository_ids: [1438229730]` и точные три permissions.

Ответ проверяется на permissions, допустимый opaque token и оставшийся срок
15–61мин, selected selection и ровно один правильный repository в ответе выдачи.
Поддерживаются длинные токены с точками; формат не считается40-символьным.
Существующий runtime cap1024bytes сохраняется; слишком длинный токен не обрезается.
Authenticated GET `/installation/repositories` с page1/per_page2 требует
total_count=1 и ровно один правильный numeric ID/full_name. Затем прежний
`validate_repository` проверяет фактические push/no-admin, disabled/archived,
protected main и exact baseline. Runtime перед AI и публикацией всё равно
выполняет свои свежие проверки; операторский receipt их не заменяет.

Contents/write и Pull requests/write сами по себе разрешают больше операций
внутри этого repo, чем задача calculator.py. Branch rules/no bypass и прежний
Gateway endpoint/task policy по-прежнему обязательны. Токен находится только
в trusted broker; его передача исполнителю или прямой publisher вне F1 запрещены.

`token_repository_count_verified=true` относится к **эффективному токену**.
`installation_repository_count_verified=false` сохраняется: scoped token не
доказывает полное число репозиториев самой установки/App. Более широкий токен
для такой перепроверки не выпускается. Scope установки отдельно проверяется
владельцем в GitHub UI; App key не передаётся агенту.

HTTP ограничен фиксированными HTTPS api.github.com paths, no redirects, timeout,
bounded response и no retry. URL из ответов не используются. Ошибки CLI не
содержат provider text, paths, JWT, token или traceback. Proxy/CA/TLS сохраняются.
Повторно проверяются owner deadline, clean source и lifetime перед сохранением.

## Неопределённый исход и отзыв

Исправленный оператор сохраняет response-bound candidate.token (fsync,0600)
сразу после первичной проверки ответа выдачи, до последующих repository GET.
Receipt содержит его SHA-256, stage, allowlisted error_code, fixed endpoint/method/
numeric HTTP status и только булевы repository checks. Raw provider messages,
токен, JWT и paths не попадают в диагностику. Неразобранная ошибка получает
фиксированный operator_check_failed. Область доступа/1024byte cap и прежний
строгий validate_repository сохраняются.

При успешных остальных проверках отдельно создаётся installation.token.
Candidate не становится runtime credential автоматически: при failure final
file не создаётся. Candidate остаётся в private каталоге для проверки без
новой выдачи. Не монтировать candidate вместо проверенного final credential.

`inspect --output-directory EXISTING_ATTEMPT --operator-revision EXACT_OPERATOR_SHA`
по умолчанию offline: читает только private receipt и metadata файлов, не PEM
или token values, не создаёт HTTP client. Legacy receipt без новых полей
показывается с UNRECORDED stage/error, а не с вымышленной причиной.

Явный `inspect --probe` использует только существующий candidate с проверенными
UID/mode/regular/no-links, SHA-256, unexpired response binding и exact scope.
App key и новое owner approval на выдачу ему не нужны. Клиент разрешает только
три fixed GET токеном: enumeration, repo, main. POST/App JWT endpoints отвергаются
самим client capability. Probe не выпускает/не отзывает токены, не записывает
файлы/receipt, не переводит candidate в final, не снимает NO_RETRY и не разрешает
deployment/расходы. Даже successful probe — отдельный readonly снимок, не
продолжение старой операции. Следующее применение требует reviewed owner решения.

Legacy попытка без candidate не может получить такой probe: значение утрачено,
новой выдачи в inspect нет. Дополнительная credential операция возможна только
после явного решения владельца по новому source/plan/каталогу; первые records
и уже выданный upstream token не объявляются отсутствующими или отозванными.

Новый каталог атомарно резервирует попытку; существующий каталог, symlink или
неверная custody отвергаются до HTTP. Receipt fsync сохраняется до POST. Crash,
одновременный дубль и повтор той же команды не вызывают новую выдачу. Каталог
нельзя удалять/переименовывать ради слепого повтора. После неудачи сначала
проверить receipt, наличие local token и фактическое состояние доступа.

При потере ответа токен мог появиться upstream. `REQUIRES_INSPECTION_NO_RETRY`
не означает, что его нет или что он отозван. При отказе записи receipt после
сохранения token файл тоже может существовать. У инструмента нет автоматической
ротации/повтора/отзыва; дальнейшее решение требует reconciliation. Отзыв App
installation/ключа или токена выполняется отдельно владельцем. Нельзя считать
истёкшим неизвестный credential раньше подтверждённого provider срока.

Исходный parent/key должны быть canonical/private0700/0600, того же UID,
regular/no symlink/no hardlink, вне source checkout. Output также вне source,
с private parent. На source/key/output change reviewed plan больше не подходит.
Receipt — локальный operator evidence, не независимая подпись GitHub, не paid
consent и не доказательство runtime/phone/rootless acceptance.

## Источники и проверка

Официальные страницы сверены29октября2026:

- [Создание installation token, repository_ids/permissions, lifetime и новый формат](https://docs.github.com/en/rest/apps/apps#create-an-installation-access-token-for-an-app).
- [Authenticated enumeration репозиториев токена](https://docs.github.com/en/rest/apps/installations#list-repositories-accessible-to-the-app-installation).
- [RS256 JWT для GitHub App](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app).

Tests используют новый disposable RSA key, настоящие private local files и
строгий httpx.MockTransport. Они проверяют JWT signature/claims, fixed endpoints,
scope, baseline, lifetime, exact source/plan, custody, concurrency, response loss,
local commit loss и отсутствие runtime/DB/AI side effects. Это не живой auth probe.
Итоговые counts и final-source CI фиксируются в Draft PR.

Последний исправленный локальный scope:657 infrastructure tests passed;
89 operator cases входят в657 и не суммируются с ним. Они включают сохранение
candidate после HTTP403/timeout и strict repository denial, safe diagnostics,
readonly probe без новой выдачи/продвижения/записей, legacy receipt и tamper guards.
Ruff/OpenAPI/current-runtime-secret guard/diff
check PASS; locked security audit:64 Python dependencies,0 Python/npm advisories,
0 Bandit MED/HIGH,99 retained reviewed LOW. Эти результаты получены до commit;
полный infrastructure suite и прежние runtime/container checks проверяются
заново на final PR merge-ref. Пересекающиеся наборы не суммируются.
