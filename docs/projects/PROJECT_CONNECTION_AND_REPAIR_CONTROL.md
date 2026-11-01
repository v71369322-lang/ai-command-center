# Подключение проекта и контур исправления

Этот этап готовит общий механизм для AI Commander. Он не подключает реальный
репозиторий и не выдаёт исполнителю GitHub credential.

## Реестр

В реестре четыре проекта: AI Commander, «Ваниль и Сахар», LNAuto и Capital Lab.
Для каждого сохранена отдельная граница риска. Telegram `/project project-id`,
`/projects`, web и API показывают одно состояние подключения.

## Проверяемое подключение

Оператор может передать в доверенный процесс только уже проверенный manifest:

- точные repository и numeric repository/installation IDs;
- default branch и исходный commit SHA;
- GitHub App выбран только для одного репозитория;
- effective permissions ровно `contents:write`, `pull_requests:write`, `metadata:read`;
- branch protection, binding и read-only probe подтверждены.

Сохранённое состояние называется `VERIFIED_DISABLED`. Оно не включает execution,
paid AI, merge или deployment. Повтор с тем же operation ID идемпотентен;
незаметная замена repository/baseline запрещена.

## План исправления

Только запрос с выбранным проектом и проверенным подключением получает локальный
план:

1. read-only анализ;
2. изменение в изолированной ветке;
3. тесты самого проекта;
4. независимая проверка результата;
5. Draft PR.

План закрепляет request fingerprint, assignment version, repository ID и baseline
SHA. Он оставляет execution, repository write и paid AI выключенными. Merge и
deployment всегда false. Отдельный последующий этап должен превратить такой план
в F1 task/grant; текущая подготовка ничего не запускает.

## Что сделать у компьютера

1. Доставить объединённый source bundle на VPS через существующий exact-approval
   release процесс.
2. Проверить Telegram `/system`, `/projects`, `/voice` и web project panel.
3. Выбрать один пилотный репозиторий и установить GitHub App только на него.
4. Выполнить read-only probe и сохранить manifest через будущий operator command.
5. Сначала провести mock/synthetic repair; затем отдельно разрешить один реальный
   AI-анализ и создание Draft PR.

До пункта 5 никакой код подключённого проекта не меняется.
