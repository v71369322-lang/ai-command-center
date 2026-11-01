# Ручной план сохранённого запроса

После PR #66 [очередь стадий подготовки](PREPARATION_QUEUE.md) показывает,
какие запросы требуют нового плана или уточнений; из неё открывается этот же редактор.

После единой карточки PR #65 владелец может подготовить план без AI-вызова:
цель, 1–8 шагов с 1–3 критериями результата и до 5 вопросов. Каждое текстовое
поле ограничено 300 символами. Автор явно обозначен как владелец. Это следующий
шаг подготовки запроса, не разрешение доступа, выполнения или расходов.

## Мобильный интерфейс

Раскройте «Подготовка запроса №N» в очереди, выберите проект и заполните «Ручной
план». Предпросмотр проверяет поля и текущие ссылки, не сохраняя документ.
«Сохранить ручной план» добавляет версию в прежний журнал. Изменение полей снимает
предпросмотр. Текущий план можно взять за основу новой версии, включая прежнее
неподтверждённое предложение; новая запись остаётся именно авторской.

При конфликте версий или потерянном ответе сохранение не повторяется автоматически.
«Загрузить текущий план» перечитывает checkpoint/карточку. Logout и закрытие
прерывают запросы; поздний ответ не восстанавливает данные. Поля, preview и
receipt проверяются в браузере, текст не интерпретируется как HTML/команды.

## Telegram

В private-owner чате `/plan_edit N` выдаёт копируемый шаблон текущего запроса:

```text
/draft_plan 1 1 2 0
Кратко: Показать выбранные публичные поля
Шаг: Подготовить вывод полей
Готово: Состав полей совпадает с согласованным списком
Вопрос: Какие поля включить?
```

После номера запроса идут версия назначения, версия настроек и последняя версия
плана; вручную придумывать их не нужно. Получите шаблон, замените placeholders,
добавьте нужные строки и отправьте. Комментарии `# ` из шаблона игнорируются.
`Готово` относится к предыдущему шагу; вопросы идут после всех шагов. Неизвестные
строки, лишние поля и неизменённые placeholders отвергаются. Большой план удобнее
править в мобильной панели. `/plan N` читает результат, `/review N` — общий обзор.

Сохранение использует прежние runtime/connection/source/owner/receive-anchor
проверки и одну транзакцию manual document + inbox DONE + reply. Дубликат update
не создаёт новую версию. Редактирование web/Telegram разделяет одну последовательность:
устаревшая запись требует нового шаблона и не затирает выигравшую версию.

## Хранение и смысл статусов

Используется существующее событие `saved_request_plan_draft`, без новой таблицы
или миграции. Старый schema 1 остаётся `owner_supplied_unverified` с прежними
provider-envelope ограничениями. Новый schema 2 — `owner_authored`, без model,
response_id, usage или выдуманного списания. Обе формы делят глобальный предел
100 документов /32768 canonical JSON bytes на документ и историю версий запроса.
UUIDv4 для HTTP и UUIDv5 от durable Telegram inbox дают одну запись на operation;
повтор с изменённым содержимым отвергается.

Schema 2 хранит request context digest, assignment version, source revision,
setup version/digest и input digest. Историческая ссылка проверяется по защищённой
истории setup. Смена назначения, Control context/source или версии настроек
делает план STALE и скрывает содержимое. Даже восстановление одинаковых настроек
в новой версии требует нового плана. DECLARED_MATCH в review означает только
совпадение сохранённых деклараций, не проверку подключения или выполнимости.
Legacy schema 1 не имеет setup binding, сохраняя NOT_RECORDED/NOT_CHECKED.

POST `/api/project-inbox/plan/preview` принимает строгий ManualRequest, POST
`/api/project-inbox/plan` — те же поля плюс operation_id UUIDv4. Owner session,
CSRF, Origin, revocation, no-store и безопасные ошибки сохраняются. Предпросмотр
не пишет документ; save пишет только прежний audit, без Task/Grant/Approval,
execution Outbox/ExternalAction или изменения бюджета. Execution/provider flags
всегда false. Обычный live planner остаётся закрытым.

Generic `/api/state` скрывает raw plan events для всех ролей; полные данные
доступны только screened owner readers. Hash/checkpoint и protected audit
сохраняются. Legacy raw-audit API reader при downgrade не обеспечивает эту privacy
границу. Известные credentials проверяются на write/read и перед Telegram send;
неизвестные секреты автоматически распознаются не всегда — не вводите их в план.

## Проверка и доставка

Real PG/API тесты покрывают версии, общую v1/v2 историю, exact bindings, shared
capacity, replay/conflict/parallel writes, rollback и роли/CSRF/revocation. Проверки
повреждённых документов включают историческую setup ссылку и audit envelope.
Telegram проверяется с private guards, duplicates, revoked connection и rollback
reply. Chromium 320/390 проверяет preview/save/edit, stale refs, lost-response
readback, checkpoint, malformed responses, logout, touch и overflow.

Existing service smoke расширен до 48 циклов /46 initial sends: template,
две ручные версии, `/plan` и `/review`; прежние семь setup версий, coding
repair/replay/mock PR и stop/resume assertions сохранены. После Control stop/resume
план ожидаемо STALE. Финальный CI использует образы из точного source SHA;
локальные старые image labels не меняются. Итоговые HEAD/merge-ref/CI — в Draft PR.

Это cloud synthetic proof. На VPS ничего не устанавливается; rootless/MFA/offsite/
iPhone/реальные AI/GitHub provider acceptance отдельно не заявлены. Frozen recovery
runtime `bf91c05c754ad41e7f89223ec8d05c02c9007de1`, старые release pairs и подготовленный
recovery пакет не меняются. Следующая доставка требует свежей host reconciliation
и отдельного точного разрешения, старые token/host окна не продлеваются.
