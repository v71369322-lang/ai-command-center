# Передача в Stage 0C-3

Класс документа: DERIVED. Stage 0C-2 заканчивается документационным PR. Тема/состав Stage 0C-3 неизвестны (U2-13); не начинать его, реализацию или инфраструктуру без следующего явного задания владельца.

Вход для следующего разрешённого пакета: точный supplied summary владельца и его provenance; тема, состав/expected counts и границы задания; оригинальные сессии/IDs/versions/аудит, если доступны. Их отсутствие остаётся явным пробелом, не заполняется invented history. Не нужны значения secrets, VPS или business credentials.

Что следующий пакет должен сверить, если затронет эти области:

1. Каждый новый supplied пункт — с сохранёнными H-A/H-B и текущими H-C/H-D, R01–R51/D01–D30; source-backed смысл отделить от DERIVED relation. Сохранять source anchor, exact text, unique ID, 1:1 register/matrix и раздельные counts exact duplicates/confirmations/refinements/extensions.
2. Project governance — primary priority/PAUSED CRM (H-C01), roadmap/knowledge/evidence (H-C02–H-C04), dependency graph/invalidation и material changes (H-C07,H-C13). Любое изменение приоритетов сверить с H-B11/H-B12 и approved incident policy H-C08, не объявляя существование такой policy доказанным.
3. Permissions и approvals — safe reversible correction H-C05, risk/exact consent/cards H-C09/H-C10, deterministic policy H-A07. Model selection H-C11 и provider capabilities H-D02 не расширяют права/резервы/доступы.
4. Autonomous development — bounded disagreement/self-repair H-D06/H-D07, layered checks и дополнительный independent AI review H-D04/H-D05, owner milestone/MVP/production acceptance H-C12. A01 не даёт права пропускать проверки.
5. Durability/agent handoff — H-C06/H-D08/H-D13: actual agent/Git/external state перед resume, checkpoints/history/artifacts/status, approved task/versions/dependencies/permissions/tests/evidence/unresolved/next-safe-actions. Не предполагать универсальные resume/stop/events/artifacts.
6. Security/release/API — H-D03/H-D10 scopes, H-D09/H-D11 exact staged release/provenance/health, H-D12 mocks/sandboxes/explicit real calls и ambiguous outcome handling. Сохранить R34: никакого auto-rollback необратимых миграций и unsafe rollback.
7. Границы — один test executor MVP, без complex multi-agent planning, real CRM autonomy/trading/analytics expansion. Capital Lab/CRM кондитерской самостоятельны; CRM автосервиса PAUSED. VPS purchased, console impairment reported, no access/configuration/test/deploy; budget ceiling не purchase permission.

Вопросы к владельцу в будущем пакете перечислены [U2-01–U2-13](CONFLICTS_AND_UNCERTAINTIES.md); они не являются запросом разрешить реализацию сейчас. Подтверждённый конфликт требует отдельной записи обеих норм и owner resolution, а не замены старой записи. Дополнения scope не распределять по MVP без решения владельца.

Передаваемые артефакты: [source](SOURCE_PACKAGE.md), [register](HISTORICAL_DECISION_REGISTER.md), [matrix](RECONCILIATION_MATRIX.md), [coverage](COVERAGE_REPORT.md), [conflicts/uncertainties](CONFLICTS_AND_UNCERTAINTIES.md), [impact](IMPACT_REPORT.md). Оба старых PR остаются не объединёнными; следующий Git base и PR target необходимо явно указать в следующем задании/отчёте.
