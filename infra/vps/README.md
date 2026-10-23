# Offline VPS preparation tools

Полный [план](../../docs/infrastructure/README.md). Никакого remote target,
SSH harness или apply/deploy helper здесь нет.

```sh
.venv/bin/python -m pytest infra/vps/tests -q
.venv/bin/ruff check infra/vps
.venv/bin/python infra/vps/validate.py infra/vps/compose.control-plane.json
.venv/bin/python infra/vps/read_only_probe.py --files-only
```

Последняя команда описывает **локальную cloud-среду**, не VPS. Полный probe без
флага добавляет только фиксированные read-only local commands, но на VPS его
запуск всё равно требует отдельного разрешения/host identity/access.

`validate.py --require-deployable ...` намеренно завершается code2: пакет содержит
незакрытые deployment gates. `x-f1-preparation` — metadata для review/validator;
сам Docker Compose игнорирует x-fields и не обеспечивает этот запрет. Нельзя
использовать `compose up` в обход процесса разрешений. JSON Compose валиден как YAML; API image/source
обязательные placeholders. Только schema parse, не pulls/containers:

```sh
F1_API_IMAGE=example.invalid/acc/f1@sha256:0000000000000000000000000000000000000000000000000000000000000000 \
F1_SOURCE_REVISION=d551cfb8dd29deb5540d9842faf704f1612d598e \
scripts/docker_local.sh compose -f infra/vps/compose.control-plane.json config --quiet
```

Digest выше **вымышленная fixture** только для парсера; не build provenance.
Не использовать compose up. Secret files из /etc/... не созданы, их права и
UID mapping не проверены. Validator — фиксированный guard review template,
не универсальный Compose security auditor и не authorization/launcher policy.
Runtime environment substitution/proxy/host network требуют отдельной проверки.

`templates/*.example` содержат unresolved identifiers; не применять как есть.
Host firewall template не заменяет Docker forwarding policy/IPv6 review.
`launcher-policy.json` — design contract, не реализованный sandbox broker.
