# Cloud handoff и готовность первого рабочего процесса

Дата: 26 октября 2026. Только документация и read-only review GitHub. Это проверка состояния PR и зависимостей, не повторный аудит всего кода и не разрешение merge/deployment.

## 1. Сохранённый план

Исходный [CLOUD-MIGRATION-PLAN.md](CLOUD-MIGRATION-PLAN.md) найден в рабочей среде: 161 строка. Он сохранён без реконструкции и без редактирования содержания.

* Ветка: `docs/cloud-development-preparation`, база #17 `53565cc2ca232fb2cf6d6552a3ae04b462d92956`.
* Первый коммит: `9f82fbe571a061a533d141d6e7ed103c91b0f87c`; только CLOUD-MIGRATION-PLAN.md, 161 добавленная строка.
* [Draft PR #18](https://github.com/v71369322-lang/ai-command-center/pull/18), base `audit/f23-first-deployment`. Выбран явный dependent PR, чтобы diff плана не включал всю реализацию относительно main. Это конкретное обоснованное отступление от общей старой инструкции AGENTS о PR в main; утверждённые границы безопасности сохранены.
* Проверки: чтение содержимого, поиск распространённых credential-паттернов (0 находок), все 19 внутренних ссылок существуют, git diff --check. Это не доказательство абсолютного отсутствия всех возможных секретов; значений реальных credentials при просмотре не обнаружено. Идентификаторы коммитов, публичные URL и наименования secret references не являются credentials.
* Утверждение исходного плана «публикация не выполняется» относится к предыдущему этапу подготовки; этим отдельным заданием владелец разрешил сохранение и Draft PR. Сам план сохранён неизменным для прослеживаемости.

## 2. Методика и ограничения review

Через GitHub REST прочитаны индивидуальные PR #2–#17: state, base/head, exact SHA, mergeable и mergeable_state; workflow runs запрошены с фильтром по каждому HEAD. Все 16 PR открыты, mergeable=true/clean на момент проверки. Это только текстовая совместимость с текущей base, не отсутствие смысловых конфликтов, не независимый security sign-off и не обещание сохранения mergeability.

Локально git merge-base --is-ancestor подтвердил **15 из 15 последовательных связей #2→#3→…→#17**. Поэтому #7 содержит историю #2–#6; #17 содержит всю последующую цепочку. Здесь не повторялось побайтовое сравнение каждого раннего документа с его исходной версией и не выполнялись тесты приложения. Зеленый старый CI не подменяет проверку будущего merge-коммита или изменённой базы.

Workflow runs на HEAD #2–#7 не найдены; не трактовать это как успешные проверки или отсутствие сторонних status contexts. У #8–#17 показаны реально найденные успешные Actions runs. CI для нового #18 проверяется отдельно; результаты #17 не переносятся на него автоматически.

## 3. Все PR: назначение, зависимости, CI и рекомендация

В колонке веток запись имеет вид **base ← head**. clean означает текущий ответ GitHub об отсутствии merge-конфликта. Все рекомендации — предложения DERIVED, не команды на выполнение.

| PR | Назначение | Ветки | Зависимости | CI на HEAD | Конфликты / устаревание | Рекомендация |
| --- | --- | --- | --- | --- | --- | --- |
| [#2](https://github.com/v71369322-lang/ai-command-center/pull/2) | Реестры 0B: требования, решения, MVP | `main` ← `docs/stage-0b-requirements` | 0A | Actions runs на HEAD не найдены (не PASS) | clean; содержимое входит в #7 | Рассмотреть закрытие как superseded после ревью #7; не сейчас |
| [#3](https://github.com/v71369322-lang/ai-command-center/pull/3) | История 0C-1: foundation/assistant | `main` ← `docs/stage-0c-1-historical-foundation` | кумулятивно #2–#2; base формально main | Actions runs на HEAD не найдены (не PASS) | clean; содержимое входит в #7 | Рассмотреть закрытие как superseded после ревью #7; не сейчас |
| [#4](https://github.com/v71369322-lang/ai-command-center/pull/4) | История 0C-2: управление проектами/разработка | `main` ← `docs/stage-0c-2-projects-development` | кумулятивно #2–#3; base формально main | Actions runs на HEAD не найдены (не PASS) | clean; содержимое входит в #7 | Рассмотреть закрытие как superseded после ревью #7; не сейчас |
| [#5](https://github.com/v71369322-lang/ai-command-center/pull/5) | История 0C-3: monitoring/security/recovery | `main` ← `docs/stage-0c-3-monitoring-security` | кумулятивно #2–#4; base формально main | Actions runs на HEAD не найдены (не PASS) | clean; содержимое входит в #7 | Рассмотреть закрытие как superseded после ревью #7; не сейчас |
| [#6](https://github.com/v71369322-lang/ai-command-center/pull/6) | История 0C-4: аналитика/инфраструктура | `main` ← `docs/stage-0c-4-analytics-infrastructure` | кумулятивно #2–#5; base формально main | Actions runs на HEAD не найдены (не PASS) | clean; содержимое входит в #7 | Рассмотреть закрытие как superseded после ревью #7; не сейчас |
| [#7](https://github.com/v71369322-lang/ai-command-center/pull/7) | История 0C-5: master plan и итоговый аудит | `main` ← `docs/stage-0c-5-master-plan-audit` | кумулятивно #2–#6; base формально main | Actions runs на HEAD не найдены (не PASS) | clean; старые текущие статусы требуют актуализации | Рассмотреть для merge исторической базы после owner review и актуальной проверки |
| [#8](https://github.com/v71369322-lang/ai-command-center/pull/8) | F1: синтетический управляющий контур | `docs/stage-0c-5-master-plan-audit` ← `feat/f1-synthetic-control-plane` | #7 и его предки | [success](https://github.com/v71369322-lang/ai-command-center/actions/runs/39990898306) | clean; более поздние PR уточняют границы | Рассмотреть для последовательного merge только вместе с review исправлений #9/#10 |
| [#9](https://github.com/v71369322-lang/ai-command-center/pull/9) | F1: отмена, audit и bounded autonomy | `feat/f1-synthetic-control-plane` ← `review/f1-security-autonomy` | #8 и его предки | [success](https://github.com/v71369322-lang/ai-command-center/actions/runs/39997921239) | clean; более поздние PR уточняют границы | Рассмотреть для последовательного merge после #8 |
| [#10](https://github.com/v71369322-lang/ai-command-center/pull/10) | F1: full-system audit и исправления | `review/f1-security-autonomy` ← `audit/f1-full-system` | #9 и его предки | [success](https://github.com/v71369322-lang/ai-command-center/actions/runs/40000980714) | clean; более поздние PR уточняют границы | Рассмотреть для последовательного merge после #9 |
| [#11](https://github.com/v71369322-lang/ai-command-center/pull/11) | Инфраструктурные шаблоны и gates | `audit/f1-full-system` ← `infra/f1-vps-preparation` | #10 и его предки | [success](https://github.com/v71369322-lang/ai-command-center/actions/runs/40028287940), [success](https://github.com/v71369322-lang/ai-command-center/actions/runs/40028287910) | clean; более поздние PR уточняют границы | Рассмотреть для последовательного merge; ранний план не инструкция текущего этапа |
| [#12](https://github.com/v71369322-lang/ai-command-center/pull/12) | Broker/watchdog/auth/backup hardening | `infra/f1-vps-preparation` ← `feat/f1-infrastructure-hardening` | #11 и его предки | [success](https://github.com/v71369322-lang/ai-command-center/actions/runs/40071519776), [success](https://github.com/v71369322-lang/ai-command-center/actions/runs/40071519853) | clean; более поздние PR уточняют границы | Рассмотреть для последовательного merge; host-specific gates остаются |
| [#13](https://github.com/v71369322-lang/ai-command-center/pull/13) | F2: ограниченный synthetic coding agent | `feat/f1-infrastructure-hardening` ← `feat/f2-autonomous-coding-agent` | #12 и его предки | [success](https://github.com/v71369322-lang/ai-command-center/actions/runs/40076715951) | clean; более поздние PR уточняют границы | Рассмотреть для последовательного merge; только ограниченный fixture workflow |
| [#14](https://github.com/v71369322-lang/ai-command-center/pull/14) | F2.1: отключённые HTTP-интеграции/финансы/publisher | `feat/f2-autonomous-coding-agent` ← `feat/f2-1-real-ai-readiness` | #13 и его предки | [success](https://github.com/v71369322-lang/ai-command-center/actions/runs/40081455827) | clean; более поздние PR уточняют границы | Рассмотреть для последовательного merge; live оставить отключённым |
| [#15](https://github.com/v71369322-lang/ai-command-center/pull/15) | F2.2: dry-run и gates первого эксперимента | `feat/f2-1-real-ai-readiness` ← `feat/f2-2-first-live-experiment` | #14 и его предки | [success](https://github.com/v71369322-lang/ai-command-center/actions/runs/40093365890) | clean; цены/FX/evidence имеют срок | Доработать актуальность внешних evidence до live; preparation может быть рассмотрена для merge |
| [#16](https://github.com/v71369322-lang/ai-command-center/pull/16) | F2.3: deployment/recovery kit | `feat/f2-2-first-live-experiment` ← `feat/f2-3-vps-deployment-readiness` | #15 и его предки | [success](https://github.com/v71369322-lang/ai-command-center/actions/runs/40124542314), [success](https://github.com/v71369322-lang/ai-command-center/actions/runs/40124542463) | clean; известные дефекты исправлены в #17 | Доработать через обязательное включение #17; отдельно не развёртывать |
| [#17](https://github.com/v71369322-lang/ai-command-center/pull/17) | Исправления boot/restart/lock/source pinning | `feat/f2-3-vps-deployment-readiness` ← `audit/f23-first-deployment` | #16 и его предки | [success](https://github.com/v71369322-lang/ai-command-center/actions/runs/40127353012), [success](https://github.com/v71369322-lang/ai-command-center/actions/runs/40127353130) | clean; host-гарантии не подтверждены | Рассмотреть для merge в его base после review; обязателен для будущего H1/развёртывания |

### Безопасный порядок рассмотрения

1. Выбрать #7 как кумулятивный кандидат для review исторической базы, проверить сохранность пакетов #2–#6, R/D/H/OPS и документационные ссылки. После отдельного решения владельца о маршруте интеграции ранние перекрывающиеся PR могут быть закрыты как superseded с ссылкой на сохраняющий историю #7. Ничего не закрывать заранее.
2. Для кода сохранить последовательность #8→#9→…→#17. Если владельцем позднее разрешены merge, после каждого изменения базы перепроверять ancestry, diff, CI и следующий target. Не выполнять squash/rebase автоматически: смена SHA может нарушить pinning и связи следующих PR.
3. Не объявлять ранние промежуточные HEAD пригодными для развёртывания: #8 нуждается в последующих security fixes, #16 — в #17. Рассмотрение merge кода не равно разрешению устанавливать его.
4. Не выполнять массовый retarget без плана: при merge в base-ветки HEAD родительских PR изменятся. Перед интеграцией нужен отдельный краткий порядок операций и повторные CI именно нового совокупного HEAD. Настоящее задание не изменяет ни одного из #2–#17.

Main на момент проверки: `9eb98cb3020db942cbd9a1377b9ccd3a34d2316e`, GitHub возвращает protected=false. Не полагаться на несуществующий обязательный технический запрет merge. Здесь действует явный запрет владельца; настройка защиты — отдельное разрешение и проверка возможностей тарифа, без покупки/изменения visibility по умолчанию.

## 4. PR #17 и VPS H1

В проверенных документах и шаблонах не найден отдельный нормативный документ с точным обозначением **VPS H1**. Поэтому нельзя выдать собственную реконструкцию H1 за согласованный источник. Далее H1 используется только как рабочее обозначение будущего первого ограниченного host/read-only шага; точный scope определяется отдельным поручением владельца.

Существующие источники: [read-only audit](docs/infrastructure/READ_ONLY_AUDIT.md), [gates G1–G5](docs/infrastructure/DEPLOYMENT_GATES.md), [актуальный deployment kit](docs/f2-3/DEPLOYMENT.md), [audit/fixes](docs/f2-3/PREDEPLOYMENT_AUDIT.md).

#17 исправляет #16: автоматический старт приложений до boot-interlock, гонку boot/update, отсутствие повторной проверки immutable source, а также неоднозначную установку доверенного operator CLI. Исходный #16 нельзя использовать отдельно как установочный комплект.

Для будущего H1/read-only полезен контекст #17, но его presence/green CI **не разрешают** SSH, установку или настройку. Перед любым реальным входом требуются официальный разрешённый cloud route, независимый host-key fingerprint, защищённый credential channel и конкретное разрешение read-only. Предыдущий неуспех cloud transport не доказывает недоступность самого VPS; сейчас сеть VPS повторно не проверялась.

После read-only находок — отдельное разрешение host preparation и отдельное разрешение закрытых synthetic trials. Проверить на хосте rootless/userns/AppArmor/cgroups, socket ACL, реальные сети, сервисы и reboot; подготовить независимые backup/checkpoints/alerts и owner access VPN/HTTPS/MFA. RPO/RTO — предварительные цели. Это не блокирует cloud coding.

## 5. Что реально готово к разработке с iPhone

Облачная разработка обычным Codex уже возможна: репозиторий доступен, файлы редактируются, коммит и push выполнены, Draft PR создан без Windows. Это фактическое доказательство пути **документация→commit→PR**, а не новый выполненный эксперимент изменения кода с тестами.

Исходники приложения, locked зависимости, Python/React, тесты и CI существуют. [F1/F2 workflow](.github/workflows/f1.yml) задаёт Python 3.12, Node 22, Ruff/OpenAPI, Vite, browser и контейнерные проверки; отдельный [infra workflow](.github/workflows/vps-preparation.yml) — инфраструктурные проверки. Docker зависит от штатных возможностей текущей сессии, не от включённого Windows.

Сам Command Center всё ещё не универсальный live AI coding agent: F2 ограничен синтетическим упражнением, F2.1/F2.2 внешние вызовы отключены, реальные credentials и платные вызовы запрещены. Разработка Command Center через облачный Codex не требует включать эти интеграции.

## 6. Одно конкретное следующее действие

**Создать с iPhone одну новую ограниченную coding-задачу Codex на базе актуального проверенного HEAD #17 (или его явно одобренного преемника), не ожидая merge всей цепочки и не используя VPS.**

Предлагаемый маленький результат: добавить в панель F2.1 постоянно видимую понятную отметку **«Учебный режим — реальные API выключены»** при режиме http_mock и браузерный regression test этой отметки. Уже существующий текст про тестовые суммы сохранить; не вводить новую авторизацию, не менять gateway и не превращать mock в live. Это улучшение видимости, не утверждение о найденной уязвимости. Не начиналось в этом задании.

Готовый текст ограниченного задания:

> Репозиторий v71369322-lang/ai-command-center. Проверь актуальный HEAD и CI PR #17; известная база 53565cc2ca232fb2cf6d6552a3ae04b462d92956. Создай feat/cloud-phone-first-task с этой базы, укажи зависимость от #17. В web/src/Integration.tsx добавь постоянную доступную отметку «Учебный режим — реальные API выключены» для http_mock. Сохрани поведение реальных/неподключённых состояний и существующие предупреждения. Расширь tests/test_mobile_browser.py: на 390×844 метка видна в mock-сценарии; mock PR не показан как реальный, горизонтального переполнения нет. Запусти Vite/TypeScript, Ruff и применимый browser test через штатную synthetic test-среду; затем соответствующий CI на итоговом SHA. Не ослабляй assertions. Сохрани коммит и отдельный PR в audit/f23-first-deployment либо актуальную явно проверенную ветку-преемник, без merge. В отчёте дай SHA, тесты, CI и ограничения. Без VPS, реальных credentials/API/данных/платежей. Разрешены обычные edits/tests/bounded fixes/commit/PR в этом scope.

До запуска уточнять архитектуру не требуется. Если выбранное улучшение уже существует в актуальном HEAD, не дублировать: зафиксировать это, выполнить недостающий regression test без расширения scope. При недоступности контейнеров выполнить независимые build/static проверки и честно оставить browser test blocked, не объявлять задачу полностью проверенной.

### Критерий завершения первого coding-процесса

* Владелец создал задачу с телефона и видит plan/progress/report в Codex.
* Есть отдельная ветка, реальное изменение React-кода, regression test и обозримый PR с правильной базой.
* Известен итоговый SHA, применимые проверки реально прошли, CI относится к нему; пропуски перечислены.
* На мобильной ширине 390×844 проверена отметка mock и отсутствие ложной ссылки на настоящий PR. Скриншот — только synthetic artifact, без секретов.
* Владелец может открыть diff, результаты Checks и отчёт в GitHub с iPhone. Это не обещание готового реального MFA-входа в Command Center.
* Нет SSH, deployment, платежей, реальных API и merge; обычные операции не требуют нового архитектурного согласования, обязательные системные prompts не обходятся.

## 7. Проверки и STOP

В этой задаче выполнены только документационный commit/push/новый Draft PR, read-only запросы GitHub и локальная проверка истории/файлов. Старые PR не изменены, не закрыты и не объединены. Проверки приложения не перезапускались, поскольку приложение не менялось. Секреты и локальные проекты не переносились, реальные серверы не затронуты.

Следующий coding-пакет выше — предложение для отдельной задачи, не исполненная разработка. После сохранения отчёта — STOP.

