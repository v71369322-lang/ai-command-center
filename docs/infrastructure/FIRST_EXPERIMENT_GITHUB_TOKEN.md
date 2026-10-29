# Подготовка GitHub credential для первого эксперимента

Продолжение [PR #46](https://github.com/v71369322-lang/ai-command-center/pull/46).
Это операторский инструмент, не новый runtime adapter или механизм grants.
Разработка и mock tests выполнены в облаке; настоящий App key остаётся на VPS.
Ни один live запрос этого инструмента пока не выполнен.

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

Пока владелец вне компьютера, достаточно cloud code review/CI. Следующие команды
описывают будущую separately authorized операцию; сейчас на VPS их не выполнять.
Операторский checkout нужно закрепить полным SHA из итогового Draft PR.
Application target `a5d867cb734a4954926a4e77c71e6f5be217057c` и восемь прежних
release profiles этим этапом не меняются. Новый runtime bundle здесь не создаётся.

1. После нового owner SSH reconciliation запустить от `acc-control` в чистом
   exact operator checkout offline `plan`:

   ```text
   .venv/bin/python infra/vps/prepare_github_token.py plan
     --key-file /home/acc-control/github-app-access/app-private-key.pem
     --output-directory /home/acc-control/github-app-access/first-token-attempt
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
   `installation.token` и redacted `receipt.json`, owner UID/0600. Не открывать
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

Локально61 targeted tests passed. Ruff/OpenAPI/current-runtime-secret guard/diff
check PASS; locked security audit:64 Python dependencies,0 Python/npm advisories,
0 Bandit MED/HIGH,98 retained reviewed LOW. Эти результаты получены до commit;
полный infrastructure suite и прежние runtime/container checks проверяются
заново на final PR merge-ref. Пересекающиеся наборы не суммируются.
