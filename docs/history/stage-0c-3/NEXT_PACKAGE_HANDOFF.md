# Передача после Stage 0C-3

Класс: DERIVED handoff. Тема/состав Stage 0C-4 ещё OPEN U3-16. До следующего explicit owner instruction не начинать 0C-4, programming, operational preflight или infrastructure actions.

Вход следующего пакета: supplied summary владельца с expected counts/IDs и provenance; точная тема, scope и Git base; оригинальные transcripts/IDs/versions/полный аудит, если доступны. Недоступное не достраивается вымышленными датами/альтернативами. Значения secrets, VPS access и customer data для документационной сверки не нужны.

Что обязательно сверить, если новый пакет затрагивает эти области:

1. Каждое supplied решение — отдельно с source/register/matrix и related R/D/H. Сохранить прежние 81 H records и различие OWNER_APPROVED_SUMMARY vs DERIVED relations/OPEN/ASSUMPTION/CONFLICT. Не выдавать 81 за число уникальных исходных решений или coverage 81/128.
2. Monitoring: technical/business-functional distinction H-E01, adaptive polling/dedup H-E02, severity/urgency/confidence/impact и quiet hours H-E03, evidence vs forecasts H-E07, timelines/RCA H-E10, шесть health states H-E12 и exact incident cards H-E13. Unknown/stale/paused не маскировать под healthy.
3. Finance: hard ceiling H-F01, actual/reserved/forecast/delayed billing + unconfirmed R36, warnings и restrict/block пороги, essential protection H-E08. Новые commitments даже ниже 10 000 ₽ требуют owner approval; essential protection не исключение для silent exceed.
4. Recovery/security: authorized safe containment/remediation H-E04/H-E11, offsite backups/tested restore H-E06, independent watchdog/alerts/console path без default second VPS H-E09/H-F03, compromise sequence H-F13. Production restore и dangerous resume требуют owner approval; planned ≠ tested.
5. Execution: actual deterministic permission enforcement/default deny H-F04, provider outage-independent controls и verified-compatible fallback H-F05, stale pins/revalidation H-F07, bounded loops H-F08, completion evidence H-F09, ambiguous-effect dependency pause H-F11, concurrency/fencing H-F12 и bounded leases/loss-of-control H-F15. Provider support не позволяет обещать instantaneous stop без evidence.
6. Data/builds: applicable localization/legal review H-F02, prompt-injection/exfiltration/adversarial defense H-F06, env separation/synthetic default H-F10, exact CI/dependency/artifact/checksum evidence и no unrestricted release secrets H-F16. Synthetic default не закрывает A01, legal compliance не выводится из языка/RUB/region предположения.
7. H-F14 provider preflight нужен до future server deployment/production, но **не выполняется** в этом этапе. VPS purchased и console impairment — сообщения владельца; readiness не проверена. Никаких предположений, что maintenance закончен. Scope real changes vs safe granted autonomy остаётся вопросом владельцу, не снимается интерпретацией агента.
8. GAP03 теперь содержит 16 audit-summary решений, но требует полного исходного аудита и его связей с H/R/D/evidence. RPO/RTO numeric targets в baseline не найдены; условные ≤15 минут/≤4 часов не утверждаются targets без нового источника, любые previously discussed targets требуют provisional feasibility treatment.
9. Сохранить one test executor MVP, отсутствие complex multi-agent planning/полноценной analytics/trading/autonomous real CRM. Новые monitoring функции не добавлять автоматически в MVP. Capital Lab/CRM кондитерской самостоятельны; CRM автосервиса PAUSED.

Открытые детали перечислены [U3-01–U3-16](CONFLICTS_AND_UNCERTAINTIES.md). Если появится подтверждённый CONFLICT — обе нормы и источники сохранить и передать владельцу, не выбирать решение односторонне. Не закрывать старые U/U2 лишь из-за импорта общего принципа.

Передаются [source](SOURCE_PACKAGE.md), [register](HISTORICAL_DECISION_REGISTER.md), [matrix](RECONCILIATION_MATRIX.md), [coverage](COVERAGE_REPORT.md), [uncertainties](CONFLICTS_AND_UNCERTAINTIES.md), [impact](SECURITY_AND_RECOVERY_IMPACT.md). PR #2/#3/#4 не объединять автоматически; текущий documentation-only PR также ждёт владельца. После 0C-3 — остановка.
