# Вход владельца по паролю: отдельный режим, ещё не установлен на VPS

Источник: прямое решение владельца в текущей беседе «не будем ставить VPN,
просто логин-пароль», затем подтверждение реализации. Это новое owner-approved
уточнение для закрытого тестового контура, не исторический H-пункт. Прежние
H/R/D не переписываются; password-only не выдаётся за MFA, полную приёмку MVP
или разрешение публичного production-доступа. Отказ от VPN не означает отключение
серверной авторизации. Telegram/голос/реальные AI API остаются следующими этапами.

## Что реализовано

* Явный `F1_AUTH_MODE=password`; OIDC с MFA и synthetic fixtures сохранены отдельно.
  Нет автоматического fallback в password/synthetic при ошибке IdP.
* Единственный owner account, стандартный PBKDF2-HMAC-SHA256 (600 000 итераций,
  случайная соль 16 байт). Реальных паролей и готового default login в Git нет.
* Приватный verifier-файл: абсолютный путь, regular file, без symlink, владельцем
  является UID процесса API, права 0600, размер <=2048 байт. Файл получает только API.
  Docker user 0 внутри rootless namespace здесь соответствует host UID acc-control.
* Неизвестный логин и неверный пароль дают одинаковый ответ. Hash проверяется
  также при неверном логине. Значения логина/пароля не записываются в audit.
* 5 попыток входа за 15 минут **включая успешные**: общий PostgreSQL-lock и audit
  сохраняют лимит между процессами/рестартами и сериализуют конкурентные запросы.
  После исчерпания ждать окно; скрытого API обхода/сброса лимита нет. Это может
  ограничить доступ владельца при атаке; текущая установка остаётся закрытой.
* Cookie-сессии: случайные token/CSRF, только их хеши в PostgreSQL, 15 минут,
  HttpOnly/SameSite Strict, отзыв одной/всех сессий, проверка срока и binding.
  Смена verifier, origin или исходной revision инвалидирует password-сессии.
* CSRF и Origin проверяются на сервере; bearer fixtures в password-mode не дают
  доступ. DB failure/audit corruption не создают сессию. Login origin обязателен.
* UI: обычные «Логин»/«Пароль», Enter/submit, блок повторного клика, очистка пароля
  после успеха/ошибки, понятные ошибки, обновление состояния и выход. Нет поля JWT.

## Транспорт

По умолчанию нужен HTTPS с точным `F1_WEB_ORIGIN`, cookie `__Host-f1-session`
с Secure. Публичный HTTP запрещён.

Для уже используемого **SSH-туннеля** есть отдельный явный opt-in:
`--owner-password-origin http://127.0.0.1:18000 --password-loopback-http`.
Он допустим только для literal loopback/localhost origin, использует отдельную
cookie `f1-loopback-session` без Secure и сохраняет HttpOnly/SameSite/CSRF.
Это не HTTPS: защита удалённого участка обеспечивается проверенным SSH, локальная
машина и браузер должны быть доверенными. Cookie не изолируется по порту браузера;
не использовать такой режим рядом с недоверенными локальными веб-сервисами.
Не пробрасывать локальный порт на LAN, не публиковать панель в интернете и не
передавать loopback-cookie на публичный host. iPhone HTTP/Safari не проверен.

Deployment renderer по-прежнему разрешает API bind **только 127.0.0.1:8000**.
Парольный режим должен быть явной частью нового manifest/bundle digest; нельзя
вручную менять compose/env уже утверждённого bundle. Старый bundle #17 остаётся
OIDC fail-closed. Никаких существующих проверок MFA OIDC не отключено.

## Будущее подключение на VPS — после проверки нового PR и exact SHA

Ничего из этого не выполнено на текущем VPS. Сначала нужны новые source-pinned
образы и проверенный compatible update, а не редактирование старого checkout.
DB schema/models/admin не меняются; исходный rollback bundle необходимо сохранить.
Одноразовый F30 runner завершился. Его prepare-helper закреплён на старом SHA
и не должен использоваться для новой revision путём обхода pinning: доставку и
сборку обновления следует выполнить отдельно через проверенный ограниченный канал.

1. В интерактивной SSH-сессии **от acc-control** запустить CLI из нового checkout:

   ```bash
   PYTHONPATH=NEW_CHECKOUT/src NEW_TOOLS/bin/python -m command_center.password_auth \
     --file /home/acc-control/f30/state/secrets/owner_password --username owner
   ```

   Новый пароль длиной 15–128 символов вводится скрыто дважды. Значение никогда
   не передаётся в чат/аргументы/runner. CLI требует терминал и не перезаписывает
   существующий файл. Для смены — отдельный защищённый файл и контролируемая замена,
   не удаление рабочего verifier без подготовки. При атомарной замене host-файла
   bind mount может остаться на старом inode: нужно контролируемое пересоздание
   API и проверка отказа старой cookie. Одна замена pathname не доказывает отзыв.
   Backup verifier — только в
   защищённой custody, отдельно от Git и обычных task artifacts.
2. После сборки exact новой revision выполнить `prepare` с прежним data-root,
   новым каталогом bundle и явными password-origin/loopback параметрами выше.
   Это не `init-state`: рабочие данные/секреты повторно не создаются.
3. Проверить digest/manifest и согласовать exact update. Existing controller
   quiesces, делает backup, сохраняет PG volume и не включает admission сам.
4. Через SSH-туннель проверить login → state → CSRF action → logout → отказ старой
   сессии. Старые синтетические проверки не доказывают безопасность реального пароля.

Обязательные будущие gates: реальная проверка обновления/отката и password mount,
долговременная сохранность verifier и recovery, HTTPS перед интернет-доступом,
отдельная приёмка владельцем. Полноценная MFA и публичный доступ не заявляются.

## Проверки разработки

Добавлены API/PG tests: успешный вход, неверный логин/пароль, private-file policy,
expiry/revocation/rotation (включая rotation во время проверки), Origin/CSRF,
HTTP/HTTPS, loopback opt-in, отсутствие bearer bypass, durable/concurrent rate
limits, DB/audit failure. Browser test использует реальную React-панель и API
на 390×844: неверный пароль → успешный login → stop → logout; секреты синтетические.
В том же browser test добавлены исходная остановка, как после установки VPS,
и resume. Он воспроизвёл 409 stale_or_recovery_resume: CSRF rotation происходила
после чтения checkpoint. UI теперь получает CSRF до snapshot состояния;
серверная проверка exact checkpoint осталась строгой.
Deployment test проверяет, что verifier монтируется только API и public HTTP
origin/изменённые настройки отклоняются. Результаты итогового SHA — в PR/CI;
никаких заявлений о проведённом VPS password-update по этим тестам не делается.
