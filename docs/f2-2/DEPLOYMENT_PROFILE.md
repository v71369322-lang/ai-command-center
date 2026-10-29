# Первый AI-эксперимент: явный профиль шлюза на VPS

Это продолжение PR #41, base `7ee0eda8d83a34aaba67d190f303b0cb8d1a56d4`.
Используются прежние Gateway, HttpCodingRunner, RuntimeBroker, F1 permissions,
финансовый ledger, verifier и deployment interlocks. Нового оркестратора нет.
Документ и успешный CI не разрешают применение на VPS или платный вызов.

## Реальный блокер подключения

На VPS владелец применил приложение `d932baafce53c0748396abfc019cf81b931ebfec`,
bundle `fcab8e820c978ff62c0fb22e78826c480f960af0416e3673552009c647c37755`.
Telegram `/readiness`, подтверждённый `/resume`, mock coding repair/verifier и
уведомление SUCCEEDED проверены владельцем. Затем владелец сообщил о `/stop`.
Это owner-provided SSH/Telegram evidence, не новый прямой cloud host probe.

OpenAI credential сохранён владельцем вне source/state на VPS, UID1000/0600.
GET model metadata вернул HTTP200, без генерации. GitHub App5524444,
installation176497504 подтвердил через подписанные GET App identity,
contents/write + pull_requests/write + metadata/read, selected selection и
binding к `v71369322-lang/acc-f2-synthetic-first`. Полное число репозиториев
установки и effective installation-token scope этим GET не проверялись.
Private key также остаётся только у владельца/VPS; cloud его не получал.

Синтетический repo ID1438229730 создан владельцем. После отдельного разрешения
cloud загрузил ровно три прежних fixture files обычным Git, без runtime publisher.
`main=a41d5fdf083fa0a162299b74ac9c155b58b140cb`; cold fetch/bytes/fsck PASS.
После настройки owner branch rule API подтвердил protected=true и тот же SHA.
Детальный protection endpoint недоступен Codex (403); PR/1 approval/enforce admins/
no force/no deletion проверены по owner form screenshots, не независимо по API.

Сохранения ключей недостаточно: прежний deployment profile явно отвергает любые
F2 integration env/mounts и оставляет broker в internal network. Этот дефект
подключения устраняется отдельным, явно выбранным binding. Старые bundles и
режим без binding остаются закрытыми и совместимыми.

## Что именно добавляется

Исходный manifest `first_experiment` содержит пять обязательных полей:
`config_file`, `config_sha256`, `profile_hash`, `openai_key_file`,
`github_token_file`. Последнее — короткоживущий installation token, **не**
App private key. Значений credentials в manifest/образах/Git нет.

Следующее cloud-продолжение добавляет единственное optional поле
`telegram_readiness: true`, выбираемое только отдельным prepare flag
`--first-experiment-telegram-readiness`. Отсутствие поля сохраняет прежний bundle;
false/строки не принимаются. Flag без config отклоняется до Docker access.

Все три host files должны быть разными canonical absolute paths вне build
context, в private0700 parents, regular/0600, UID control, без symlinks/hardlinks.
Config ограничен16KiB. Credentials проверяются по metadata/size16–1024 bytes;
prepare/preflight не читают их значений. В частности App PEM сюда не подставляют.
Исходные App private key и Windows SSH key контейнерам не передаются.

Config использует прежний IntegrationConfig, exact first experiment/model,
context400000/output2048, выделенный synthetic repo ID, положительный confirmed
tariff и budgets не выше100₽. `http_mock`, произвольная модель/репозиторий,
нулевая цена или превышение capacity этим live-capable профилем не допускаются.
Наличие этого профиля не является подтверждением истинности тарифного evidence.

В JSON ссылки на container files должны быть ровно такими:

```json
{
  "openai_secret_ref": "openai",
  "github_secret_ref": "github-installation-token",
  "credential_files": {
    "openai": "/run/f2/openai.key",
    "github-installation-token": "/run/f2/github.token"
  }
}
```

Это только fragment структуры, не готовый live config, не ключи и не разрешение.
Другие distinct aliases возможны, если они однозначно соответствуют этим двум
фиксированным container targets и нет дополнительных credential references.

API и broker получают readonly `/run/f2/config.json` и его обязательный byte
SHA-256 через `F2_INTEGRATION_CONFIG_FILE`/`F2_INTEGRATION_CONFIG_SHA256`.
Только broker получает два readonly credential mounts и `gateway-access` network.
С opt-in `telegram_readiness` Telegram также получает только pinned readonly config;
его прежние сети/DB-only secret scope сохраняются. Worker, watchdog и
coding/verifier sandboxes не получают ни этих
credentials, ни integration config, ни gateway network. Loopback API, отдельный
execution daemon, image/source pinning, read-only root/cap drops/resource limits
и прежний boot/halt/recovery порядок сохраняются.

Docker non-internal network даёт broker egress; это не firewall по доменам.
Фиксированные endpoints/no redirects/task authority остаются в прежнем Gateway.
TLS и rootless/AppArmor не отключаются. Новых proxy/host-network исключений нет.

`profile_hash` — существующий Gateway digest; он исключает credential references.
Поэтому отдельно закрепляются **все исходные JSON bytes**, включая references.
IntegrationConfig.load проверяет byte pin до возврата config каждому процессу.
Подмена reference на DB password или изменение operator flag не проходят.
Новый pin optional только для прежнего standalone loader; в opt-in deployment
он обязателен. Прежний loader дополнительно читает bounded O_NOFOLLOW descriptor.

## Подготовка и применение

`deployment prepare` принимает три новых явных аргумента одновременно:

```text
--first-experiment-config PRIVATE_CONFIG
--openai-key-file PRIVATE_OPENAI_KEY
--github-token-file PRIVATE_INSTALLATION_TOKEN
```

Без всех трёх нет нового профиля; неполный набор отклоняется до Docker access.
На других actions эти аргументы не игнорируются, а отвергаются. Config/file
custody и оба hashes проверяются при prepare и каждом deployment preflight.
Postcheck проверяет hashes внутри API/broker и opt-in Telegram, actual readonly mount metadata
всех служб; ключ в API/worker/watchdog/Telegram или writable bind отвергается.

Оператор использует прежний build_release.sh на двух rootless daemons,
prepare/inspect/exact approval/update/postcheck. Operator helper
`infra/vps/stage_telegram_update.py` получает отдельный `--release first-experiment`:
приложение `d932baafce53c0748396abfc019cf81b931ebfec` →
`0d44f31fe9e37045ed410751cbac7020c59b669a`. Этот полный application SHA
предшествует operator-only commit, содержащему именованный переход; operator
checkout и application checkout закрепляются отдельно. Старые три release profiles
и default f34 не меняются. Новый profile требует явный binding только в candidate;
через старое имя подключение integration отвергается. Stage и apply под lock
перепроверяют config pin и custody до записи candidate/остановки Telegram.
Нельзя вручную подменить connection.json или использовать compose override/up.
Согласование source/build/stage отдельно от exact candidate apply сохраняется.
Нового готового host bundle digest, source checkout или image IDs в облаке нет.

Config — immutable snapshot. Изменение flags/evidence/tariff/paths меняет pin и
требует нового inspect/bundle/approval; редактирование live файла приводит к
отказу. Не продлевать истёкшее owner окно и не сбрасывать activation journal.
При неопределённом результате сначала сверять state/journals/службы.

`live_authorized=false` допустим в подготовленном профиле: ключи уже могут быть
смонтированы в trusted broker, но Gateway.connected остаётся false. Даже true
не выдаёт task grant. Все9 expiring gates, истинная payment upper bound,
budget/usage/unknown reserves и exact final owner confirmation проверяются
прежними runtime guards. Эти финансовые/permission проверки не менялись.
Два вызова — максимум, не обязательное число; прежний monthly90% stop сохраняется.

## Проверки и ограничения

Локальные policy tests проверяют legacy defaults и byte pins, all-or-none CLI,
mount/network/env expansion, private custody и config mutation, source context
exclusion, App-PEM size rejection, отсутствие чтения key values/HTTP/Store/grants,
postcheck actual mount metadata и работу прежнего отказа при missing gates.
Fake engines/DB в этих tests явно обозначены; это не VPS/rootless acceptance.

Проверенный локальный combined run: **467 passed /1 прежний Starlette-httpx
warning** —129 deployment/pin tests и338 infrastructure. Новые61 входят в129;
58 offline preflight входят в338. Пересекающиеся наборы не складываются.
Ruff/OpenAPI/TypeScript/Vite PASS. Полный локальный dependency/static audit:
64 Python dependencies,0 Python/npm advisories,0 Bandit MED/HIGH,92 reviewed LOW.
Эти результаты получены на рабочем tree до commit; final SHA проверяется CI.

После добавления именованного operator transition: **353 passed /1 тот же warning**
(224 staging tests, включая четвёртый release profile и отказы до pause/journal,
плюс те же129 deployment/pin tests). Это пересекающийся targeted run, не353
дополнительных теста. Ruff/OpenAPI/current-runtime-secret guard/diff check PASS.

`scripts/first_experiment_profile_smoke.py` добавлен в полный verify_cloud.sh:
fresh exact-revision images, настоящие network=none контейнеры API/broker/worker,
public fake credentials во временном private directory вне build context.
Проверяются API без key files, readonly keys только в broker, закрытый worker
и отказ при изменённом credential reference с прежним byte pin. Script не
использует реальные keys, DB, provider API или публикацию PR. Результат будет
доказательством только после выполненного финального CI, не по наличию script.

Временный cloud workspace имеет ограниченный диск; локальная пересборка старых
образов без нужды не выполняется. Полный Python/HTTP-mock/container/security CI
запускается на новом final SHA в чистом GitHub runner; результаты фиксируются
в PR. Наборы policy/infra и полного Python не складываются.

Live всё ещё требует: verified all-in payment bound вместо приблизительного
курса; current pricing/funding; проверенный selected repo count и installation
token с нужной expiry; актуальный host runtime/profile dry-run; новое exact
deployment approval и отдельное окончательное paid approval. Сейчас paid calls=0,
автоматического merge нет, CRM/production не затрагиваются, production-ready
и физическая iPhone-приёмка нового профиля не заявляются.
