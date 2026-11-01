# F34: результат применения на VPS 28 октября 2026

Происхождение: владелец выполнил согласованные команды в собственной SSH-сессии
и прислал их текстовый вывод и Telegram Web screenshots. Cloud не входил на VPS;
это owner-provided host evidence, не подписанные F33 receipts и не независимый
новый опрос хоста. Скриншоты с посторонними чатами/персональными данными в Git
не включаются.

- Исходники: `v71369322-lang/ai-command-center`, application checkout
  `b2e71fe073f3109e639dac43496884905ce86d9f`, operator checkout PR #36
  `364c5eb4b44ad4ab743cacd9ae1d204866bd0d6c`.
- Отдельный VPS read-only deploy key зарегистрирован владельцем в этом repo
  после инструкции оставить Allow write access выключенным. Административной
  API-проверки этого флага из cloud не было. Private key не передавался.
- `git ls-remote` дал `F34_GITHUB_READ_OK`. Prepare service invocation
  `098ad63318714097bf385b29c400352f` завершил существующую сборку target и staging.
- Предшествующий live bundle:
  `0ee8a6023296fdacfe632c2f364c488b2564db399bfd15af357812e41004d64b`.
- Disabled preparation bundle:
  `bd1cb6de43c4e19cf2a28590997bbea6226e1856d05a840826a2d6660a60494b`.
- Candidate/live target bundle:
  `a1cf9b0d783cc15a17e8d119167008a81584a051bcd55a0e9b359c519d8be9c8`.
- Staging вернул STAGED_NOT_ACTIVATED, live_binding_modified=false и
  `F34_CANDIDATE_PREPARED_NOT_APPLIED`. Затем отдельное явное «разрешаю» владельца
  охватило именно этот update, с дедлайном `1793218803` (23:20:03 МСК 28 октября).
- Update service invocation `ec1104394c254f94ade277f49e1a7bfd` завершился:
  Result=success, ExecMainStatus=0, inactive/dead. Это штатно завершённый oneshot,
  не постоянная служба приложения. Activation journal: phase=VERIFIED,
  expected_previous и target совпадают с приведёнными digests.
- Apply/postcheck вывели CLOSED_SYNTHETIC_SERVICES_RUNNING, затем
  `F34_UPDATE_VERIFIED`. По коду update делает quiesce/encrypted backup/stop/
  immutable image update/postcheck. Отдельный offsite/restore drill именно этой
  резервной копии в текущей host-приёмке не выполнялся.

## Telegram после обновления

Владелец подтвердил screenshot-ответами:

1. `/start` отвечает обновлённой справкой.
2. Текст «Тест F34: проверить выбор проекта» сохранён под №131179132.
3. Inline-выбор AI Commander подтверждён как версия назначения 1.
4. Независимый `/request 131179132` показал тот же текст/проект/версию.
5. Прежний `/request 131179125` доступен, исходный текст сохранён,
   проект «Не распределён», версия 0; ему назначение не задавалось.
6. `/coding_plan` показывает фиксированное mock-упражнение f2-synthetic-sum,
   calculator.py, до 2 iterations /2048 synthetic tokens /15 секунд /2 units.

Это desktop Telegram Web acceptance; отдельной проверки F34 на iPhone пока нет.
Полный coding execution/repair/verifier/notification именно после этого update
пока не выполнен: обычная остановка сохранена, владелец отошёл от компьютера и
не может открыть панель через прежний Windows SSH tunnel. Команды чтения не
снимают остановку и не создают business execution.

В postcheck остаются false: go_live, owner_mfa_verified,
rootless_execution_smoke_verified, offsite_verified. Реальные AI/voice/CRM,
GitHub publisher и внешняя HTTPS-панель не включались. Старый диагностический
F33 grant истёк и не продлевался; F34 был отдельной точной owner SSH operation.
Перезапускать F34 apply нельзя: activation journal уже VERIFIED, нужно читать
активное состояние и отдельно согласовывать любые новые host changes.
