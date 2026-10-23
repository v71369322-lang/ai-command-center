# Закрытое управление с iPhone — рекомендуемый вариант

**DERIVED выбор:** Tailscale private tailnet → private HTTPS → отдельный MFA
gateway → loopback F1 API/web + собственная synthetic app authentication.
Причина: мобильный клиент, device revocation/ACL, NAT traversal и возможность
штатного managed-cloud VPN подключения; без собственного публичного домена.
Это дополнительный security access component, не новый бизнес-модуль.
Аккаунт/условия/регион/стоимость/наличие cloud VPN credentials ещё не проверены.
Ничего не зарегистрировано. IdP login MFA не заменяет MFA входа в приложение.

## Target layout и контроль доступа

1. Владелец устанавливает официальный VPN-клиент на iPhone только после разрешения
   подключения сервиса. Устройство регистрируется через защищённый процесс,
   MFA IdP, ограниченный tailnet, device expiry/revocation.
2. Адрес HTTPS выделенного VPS доступен только внутри VPN; интерфейс proxy bind
   к проверенному VPN address, не 0.0.0.0. HTTPS сертификат проверяется Safari.
   Вариант provider-managed tailnet certificate/MagicDNS требует отдельного
   согласования и фактической проверки; DNS/сертификаты сейчас не создаются.
3. Reverse proxy (например Caddy) выполняет fail-closed forward-auth в self-hosted
   MFA gateway (например Authelia с паролем + TOTP). MFA UI доступен только VPN.
   Обычная сессия и step-up для critical actions проектируются/test отдельно.
4. Proxy не принимает trusted identity headers от клиента. Backend/gateway только
   loopback/internal, bypass `/api`, websocket, alternate host/IPv6 paths закрыт.
   Admin API/PG/Redis/Docker на публичных IP не публикуются. Tailnet SSH identity
   и app owner identity не объединяются автоматически.
5. F1 пока требует отдельный synthetic bearer. Не вставлять owner bearer в JS
   bundle, proxy config/Git или blanket inject credential каждому VPN-пользователю.
   MFA gateway session не является runtime task approval. Реальная app MFA и
   безопасная identity/session integration требуют отдельной реализации/испытания;
   данный пакет их не подменяет. До этого authenticated VPS UI gate закрыт.

Cookie gateway: Secure/HttpOnly/SameSite, CSRF защита, bounded lifetime и logout/
revocation; TOTP drift/rate limits/recovery codes. Рекомендованный DERIVED session
idle 15 min, max 8 h, sensitive step-up ≤5 min — профиль для будущего review,
не уже действующие значения. Изменение F1 cookie/CORS потребует новых API tests.
Tailnet policy [example](../../infra/vps/templates/tailnet-policy.hujson.example)
разрешает owner только443, отдельному cloud auditor только22, остальное deny.
Никаких Funnel, exit node, subnet router или маршрутов к CRM.

## Cloud Codex и телефон

Managed cloud VPN connection настраивается штатным механизмом платформы с
отдельным scoped identity/ephemeral credential; это не личный SSH key владельца.
Текущая среда VPN не имеет. Если провайдер/платформа не поддерживает выбранный
маршрут, безопасно блокировать доступ; не открывать публичный SSH всему Интернету
и не использовать CRM как relay. Вся работа возможна с телефона через cloud и
provider console, без пользовательского ПК.

## Потеря телефона / компрометация

До go-live: offline recovery codes MFA, второй доверенный способ восстановления
IdP, отдельная защищённая копия backup/decryption keys и provider recovery.
Не хранить все факторы только на одном iPhone или на VPS. После потери: через
независимый trusted channel отозвать device/VPN/app sessions, остановить admission,
проверить audit, rotate exposed credentials. Не отключать MFA ради возврата доступа.
Если нет второго устройства/независимой recovery capability, RTO4h не гарантируется.

Аварийный путь — provider console/rescue + точные команды остановки dedicated
runner/admission после отдельного разрешения, не неограниченный SSH у AI-агента.
Неисправная provider panel сейчас — реальный blocker восстановления/изменений.

## Альтернатива без coordination SaaS

Self-hosted WireGuard, split tunnel только адрес F1, private CA/HTTPS и тот же MFA
gateway. Нет лицензии VPN-сервиса как обязательной статьи, но остаются обслуживание,
безопасная выдача/отзыв ключей и доверие к CA на iPhone. Нужен поддерживаемый cloud
маршрут; установка WireGuard на облачного исполнителя не считается автоматически
допустимой. Рекомендованный вариант проще для phone-first эксплуатации, альтернативу
выбирать при недопустимых условиях/стоимости SaaS в отдельном review, не подключать сейчас.
