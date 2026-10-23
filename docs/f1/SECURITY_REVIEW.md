# Критическое ревью F1: текущая облачная итерация

Это review выполняющего агента, не отдельное независимое заключение другого
reviewer. Независимый verifier результатов исполнения — отдельный механизм и
не заменяет независимое review значимого изменения H-D05/H-I10.

## Исправления

| Находка | Последствие | Исправление / проверка |
| --- | --- | --- |
| CANCEL_REQUESTED превращался в RECONCILING при expired lease | После сверки отменённая операция могла стать кандидатом owner retry | Сохраняется намерение отмены; regression test запрещает retry после reconciliation |
| compare_digest(str) не принимал не-ASCII credential | Неавторизованный запрос мог вызвать 500 | Сравнение bytes, ограничение длины; negative auth test |
| Короткий контейнер мог завершиться до inspect | Результат принимался без фактической проверки isolation metadata | Обязательный inspect перед принятием результата; fail closed/security trip |
| JSON true сравнивался с integer fence 1 | Нарушение строгого контракта manifest | Проверка точного типа int перед сравнением |
| Validation error мог повторять входные данные | Случайный секрет мог попасть в error response | Общий безопасный 422; OpenAPI обновлён; negative echo test |
| Secret fields попадали в dataclass repr | Возможная утечка при диагностике | repr=False для credentials; regression test |
| UTF-8 данные раздувались ASCII-escaping между API и executor | Валидная Unicode-команда могла превысить input limit | Ограничение байтов и компактный UTF-8 transport; real executor regression |
| Resume при ещё неизвестном исходе | Некорректное представление готовности контура | Запрет до завершения reconciliation; pending grants отзываются |
| Forecast не учитывался в отображаемом threshold | UI мог показывать 0 при budget restriction | Threshold по max(actual+reserved, forecast); regression test |
| Audit denial блокировал async event loop | Риск задержки управляющих запросов | Offload в bounded thread pool; bounded HTTP rate state |
| Worker получал owner/operator bearer secrets | Ненужные credentials у launcher | Worker не монтирует identities; API/agent boundaries сохранены |

## Решения в пределах разрешения F1

- Контейнерный worker — тот же доверенный launcher с полномочиями локального
  облачного Docker daemon, а не новый административный сервис. API/executor
  socket не получают. Никакого privileged/host networking или доступа к VPS.
- Docker CLI закреплён digest; app/worker — разные build targets. Секреты
  остаются runtime mounts, в образ не копируются.
- 60 requests/min/IP и bounded LRU на 1024 источника — DERIVED профиль F1.
  Это дополнительная защита, не durable authorization и не distributed rate limit.
- Audit проверяется streaming batches, без загрузки всей цепочки в память.
- Дополнительный restore drill использует другой контейнер PostgreSQL, tmpfs,
  network=none, без портов. Local trust включён только в disposable drill;
  primary PostgreSQL settings не меняются. Это не offsite disaster recovery.

## Не закрывать без внешнего evidence

Host-compromise isolation, независимая custody/immutability checkpoints/backups,
key escrow, watchdog и emergency access, VPN/HTTPS/MFA и реальные VPS quotas.
Контейнеры одного Docker daemon не являются независимыми failure domains.
RPO≤15min/RTO≤4h остаются provisional. Исходные owner requirements не ослаблены.
