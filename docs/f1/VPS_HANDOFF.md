# Будущий VPS: отдельное разрешение, не инструкция немедленного запуска

Новый VPS 176.12.75.135: Алматы/Ubuntu 24.04/4 vCPU/8GB/80GB NVMe — сообщение
владельца по панели, НЕ аудит ОС. Панель провайдера неисправна по сообщению.
CRM 206.223.246.79 и другие серверы не трогать, не использовать как jump host.
В текущей разработке не выполнялись SSH-вход, TCP probes или удалённые команды.

До размещения:
1. Независимый SSH host key; защищённый credential; отдельное разрешение read-only
   аудита и разрешённая платформой сеть. Не использовать StrictHostKeyChecking=no.
2. Read-only OS/resources/load/network/ports/services/containers/rights/isolation
   без secrets/customer data/install/update/restart/load tests.
3. Подтвердить отсутствие влияния на другие проекты и достаточные резервы.
4. Review trusted launcher/Docker authority; закрытые сети/volumes/accounts,
   реальный VPN/admin access, application auth/MFA, firewall/HTTPS.
5. Применимый authorized provider/legal/cost preflight до размещения; реальные
   AI/Telegram/business API не тестировать в F1 под видом preflight.
6. Согласовать конкретные изменения сервера, внешние backups/checkpoints/key
   custody/watchdog и расходы. Hard ceiling 10 000 RUB не permission purchase.
7. Проверить pinned source/image provenance, CI, миграции, backup/rollback.
8. Только после разрешения — перенести Compose-конфигурацию под audited UID/
   secrets/ресурсы и изолированный synthetic environment; никаких публичных портов.
9. Повторить T01–T14, restore в независимый контур, измерить RPO/RTO, проверить
   аварийный доступ без AI/control plane. Owner acceptance отдельно.

Не применять cloud resource profile как доказанную спецификацию сервера.
Production release/данные/реальные интеграции/merge/следующий этап не разрешены.
