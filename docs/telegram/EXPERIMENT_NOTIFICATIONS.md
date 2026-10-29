# Уведомления о первом AI-эксперименте

Cloud-продолжение [PR #44](https://github.com/v71369322-lang/ai-command-center/pull/44).
Source target предыдущего пакета не включает новые команды. VPS пока не менялся.

Operator profile `--release first-experiment-notifications` закрепляет d932baaf →
`8bab523f6f6e50a8a63e13a094f7fccf59ca889f`. Требуются прежние private file
bindings и readiness opt-in; подписка всё равно выключена до явной команды
владельца. Один кандидат включает gateway/readiness/snapshot/notifications;
старые targets не переименовываются. Operator checkout закрепляется отдельно.
Host prepare и exact candidate apply approval остаются отдельными этапами.

## Использование после доставки

`/watch_experiment` без аргументов подписывает личный чат владельца на исход
существующей фиксированной API-задачи. Если задача ещё не создана, подписка не
включается и не переносится на будущую задачу. `/experiment` по-прежнему даёт
снимок и сам не подписывает. `/unwatch_experiment` отключает дальнейшие уведомления.
Команды не запускают AI, не выдают grants и не разрешают расходы.

Сообщение появляется для SUCCEEDED, FAILED, CANCELLED, RECONCILING или
SECURITY_BLOCKED. Его текст — тот же проверенный snapshot первого эксперимента:
recorded mode, outcome, расходы/резервы по журналу, лимиты и допустимый cached PR
link. Live и HTTP-моки различаются; необоснованный успех или произвольные
provider/evidence/артефакт-тексты не отправляются. Это не remote health/balance probe.

Повторный опрос, время снимка, несколько collectors и перезапуск не создают
дубли. Новое видимое состояние или изменение сумм может создать новое сообщение.
Например, billing settlement с нулевым резервом не подтверждает результат:
SETTLED сохраняет требование сверки и запрет автоматического повтора.

## Согласие и доставка

Подписка хранится в прежнем append-only audit, без новой таблицы/permission system.
Её запись привязана к owner/private-chat получению команды, immutable inbox intent
и fingerprint, завершённому receipt, профилю подключения, task ID/payload и source.
Фантомная запись audit без соответствующей команды не разрешает уведомление.
Новый source не продолжает старую подписку автоматически; её отключение допускает
отзыв старых ожидающих уведомлений того же owner/profile.

Collector использует прежнюю transaction/admission/audit блокировку и
TelegramDelivery. Ключ — digest source и проверенного видимого текста без UTC-
времени. Текст сообщения сохраняет UTC-время фактического создания снимка.
Уже существующая delivery никогда не превращается в повтор новой подпиской.
Сами watcher commands, snapshots и их подтверждения не затрагивают F1 tasks,
approvals, Outbox, financial grants/actions или резервы.

При отключении отменяются только известные experiment notices в NEW, с проверенной
связью audit/delivery ID. Ответы на команды остаются. Новая CANCELLED запись
означает отменённую **отправку**, не отмену задачи; SQL-схема не меняется.
SENDING, SENT и UNCERTAIN сохраняются: уже начавшаяся отправка может завершиться
после unsubscribe. Неизвестный send не повторяется после recover/restart/re-enable.
Ранее отменённое сообщение тоже не переотправляется: текущий итог — `/experiment`,
новые видимые изменения после повторного включения получают собственный ключ.

При обычной остановке/recovery информация остаётся доступной без resume.
Подписки других подключений не читаются. Четыре прежние кнопки меню сохранены;
help и snapshot содержат команды подписки. В состоянии default-off collector
не читает Gateway/credentials и не создаёт HTTP client; при active он использует
прежний проверяющий snapshot, не выполняя provider API или reconciliation.

## Проверки и границы

Локальные PG/strict Bot API tests покрывают default-off, явную подписку,
terminal/nonterminal outcomes, concurrence/restart/clock dedupe, смысловые изменения,
unsubscribe/queued cancellation, исходы начатой/потерянной отправки, source rotation,
crash rollback, foreign/private-owner checks, forged receipt и numeric JSON tampering.
Cached live-record fixtures проверяют отображение, не реальную публикацию.
Существующие full-pipeline HTTP-mock sandbox tests дополнены subscribe → poll →
одна notice → повторный poll без дублирования для success/wrong-repo/response-loss.

Первый локальный combined run:198 passed /2 failed из-за expected source/image
revision mismatch в двух прежних container cases. Старые images не перелабеливались,
проверка pin не ослаблялась. Эти cases требуют clean exact-source images в CI.
Повторный локальный scope без этих двух container cases:198 passed /2 deselected
/1 Starlette-httpx warning; 34 новых watcher cases входят в этот набор и не
суммируются с ним. Ruff/OpenAPI/current-runtime-secret guard/diff check PASS;
locked audit:64 Python dependencies,0 Python/npm advisories,0 Bandit MED/HIGH,
92 retained reviewed LOW. Эти проверки сделаны до source commit; final SHA — в CI.
Named staging transition:360 passed, все семь release profiles. Это отдельный
infrastructure run; его пересекающиеся cases не суммируются с другими наборами.
Окончательные suite counts, source/PR/CI и выполненные container результаты —
в отдельном Draft PR. Rootful cloud tests не являются rootless VPS/systemd или
физической phone-приёмкой. Реальные сообщения бота, AI-вызовы и runtime PR не выполнялись.
