# Автономность текущей облачной среды

## Факты и пределы диагностики

Проверена managed cloud-среда текущей сессии. Файловый sandbox — workspace-write,
доступны рабочие пути /workspace и /tmp; .git/.codex и другие защищённые пути
могут иметь отдельные правила. HTTP policy: enforced/unrestricted; VPN не
настроен, TCP grants отсутствуют. Это не доступ к VPS.

Обычные apply_patch, запись файлов проекта, git branch, локальные статические
проверки выполняются штатно. Docker Unix socket в обычном sandbox даёт
`connect: operation not permitted`. Та же команда с официальным per-command
`with_additional_permissions`/`network.enabled=true` получает Docker 28.4.0.
Следовательно, наличие клиента и права socket на уровне ОС недостаточны:
ограничивает sandbox. Это не неисправность Docker и не запрет проекта.

Причина конкретного пользовательского диалога может также включать execution
policy/reviewer или аннотации connector. Runtime tools не показывают полный
active approval policy, reviewer setting, журнал UI prompts или настройки
аккаунта. Поэтому нельзя утверждать точную причину каждого прежнего запроса
или доказать полное отсутствие будущих prompts только успешным tool result.

## Что официально поддерживается

Проверены официальные страницы OpenAI (HTTP 200):

- [Sandboxing](https://learn.chatgpt.com/codex/sandboxing)
- [Auto-review](https://learn.chatgpt.com/codex/sandboxing/auto-review)
- [Agent approvals/security](https://learn.chatgpt.com/codex/agent-approvals-security)
- [Cloud environments](https://learn.chatgpt.com/docs/environments/cloud-environment)
- [Cloud internet access](https://learn.chatgpt.com/docs/cloud/internet-access)

Auto-review/«Approve for me» официально существует: eligible boundary requests
проверяет отдельный reviewer, sandbox остаётся. Это не blanket allow и не
детерминированная policy будущего Command Center. Документация описывает
переключатель под полем ввода **desktop**; local CLI имеет соответствующие
настройки. Установленный CLI действительно показывает `--approve-for-me`,
но запуск дочернего CLI не перенастраивает текущий cloud orchestrator и не
используется как обход. Local config.toml/`--ask-for-approval never` не являются
подтверждённой настройкой этой мобильной cloud-сессии. Защиту не отключали.

## Действия владельца с iPhone

1. Если используется ChatGPT Work и настройка доступна: Settings → Data controls
   → Work network access → Allow public internet access. Это **только сеть**,
   не выключатель command approvals. Текущая сеть уже unrestricted, поэтому
   менять её ради Docker не требуется.
2. Документация прямо указывает: ChatGPT web не показывает local Codex sandbox/
   approval-mode selector. Нельзя обещать, что Safari «версия для компьютера»
   создаст такой переключатель. Подтверждённой последовательности включения
   Auto-review именно на iPhone для текущей среды не найдено.
3. Если сам диалог платформы предлагает разрешение «на сессию», можно выбрать
   самый узкий scope для разрешённой облачной работы; наличие этой опции здесь
   не подтверждено. Не давать blanket доступ к серверам и данным.
4. Если prompts сохраняются, администратору/поддержке платформы передать:
   «Нужен поддерживаемый auto-review для bounded cloud workspace и Docker
   synthetic tests; обычный sandbox блокирует Unix socket EPERM. Не требуется
   VPS, Full access или отключение sandbox. Есть ли такой режим для нашего
   cloud/mobile клиента и разрешает ли его workspace policy?»

Из текущей сессии нельзя менять глобальную policy, выбирать reviewer аккаунта
или гарантировать отсутствие ручных prompts. Проблема **не объявляется решённой**.
Уже применено: native apply_patch, рабочая папка, batch проверок, узкие официальные
additional permissions, GitHub connector вместо лишних сетевых shell-команд.

## Будущая система

[R-F1-AUTO-01](../requirements/AUTONOMOUS_EXECUTION.md) требует stage grants,
least privilege, deterministic policy, noninteractive compatible providers,
bounded repairs и evidence. Provider Auto-review не заменяет эти механизмы.
Неподдерживаемый provider безопасно блокируется/заменяется в разрешённых рамках.
Ни UI auto-clicking, ни доступ к реальным системам в F1 не добавляются.
