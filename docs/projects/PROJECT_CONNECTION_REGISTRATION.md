# Регистрация проверенного подключения проекта

`infra/vps/register_project_connection.py` переносит уже проверенное оператором
доказательство в audit-журнал AI Commander. Оператор не обращается к GitHub,
не читает токены и не запускает задачи. Итоговое состояние всегда
`VERIFIED_DISABLED`: execution, paid AI, merge и deployment остаются выключены.

## Доказательство

Входной JSON создаётся отдельной проверкой GitHub App и репозитория. Он содержит
строго один manifest с project ID, фиксированным repository из каталога, GitHub
repository/installation IDs, default branch, baseline SHA, минимальными правами и
булевыми подтверждениями selected-only scope, binding, branch protection и
read-only probe. Неполное доказательство и repository, не совпадающий с каталогом,
отклоняются.

Файл должен находиться вне checkout, принадлежать выделенному непривилегированному
оператору, иметь режим `0600`, одну hard link и родительский каталог `0700`.
Символические ссылки и файлы больше 32 KiB запрещены. Содержимое или путь файла
не выводятся в публичный результат; план связывает его SHA-256, manifest, точный
чистый operator revision и канонический operation UUID.

## Два шага

1. `plan` выполняет только локальную проверку и возвращает
   `OFFLINE_PLAN_NOT_AUTHORIZED` с `plan_digest`.
2. `apply` требует точного digest, owner deadline не дальше десяти минут и
   совпадения runtime source binding с проверенным operator revision. Затем прежняя
   транзакционная функция `project_connections.register` проверяет audit chain и
   записывает идемпотентное событие.

Повтор с тем же operation UUID и тем же manifest безопасен. Замена уже
зарегистрированного репозитория требует отдельного disconnect-перехода. Ошибка
после записи не может расширить полномочия: сама запись не выдаёт права выполнения.

Для первого подключения AI Commander ещё нужно переключить GitHub App на
`v71369322-lang/ai-command-center`, получить свежее selected-only evidence на
текущем baseline и отдельно применить будущий оператор на VPS. Этот документ и
Draft PR не выполняют эти действия.
