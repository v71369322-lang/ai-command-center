# F33: продолжение после отсутствия владельца

На момент паузы Cloud SSH недоступен; для обычной облачной разработки Windows
не нужен. Реальный Telegram уже проверен на iPhone: сохранение и чтение запроса,
а также результат синтетического исполнителя. Это не проверка настоящего AI.

Последний подтверждённый host-вывод: /usr/sbin/runuser и /usr/bin/prlimit есть,
runuser отсутствует в ограниченном PATH, enrollment_files_present=false.
После этого был выдан исправленный блок установки, но его успешного результата
нет. Нельзя считать ни установку успешной, ни текущее состояние файлов известным.
Предыдущее окно первоначальной установки до 14:58 МСК 28 октября 2026 истекло.
Никакой автоматической регистрации, активации или продления политики не будет.
Старые длинные блоки не повторять, срок действия и digest не менять вручную.

## Когда владелец вернётся: только одна read-only проверка

После обычного проверенного SSH-входа этот блок не требует новой доставки кода.
Он проверяет наличие файлов и читает только публичные метаданные установки,
принадлежащие root. Ключ подписи, пароль, токен бота и credentials runner не читаются.

```bash
python3 -I - <<'PY'
import json
import os
from pathlib import Path
import stat

paths = ['/etc/acc-operations', '/usr/local/lib/acc-operations', '/var/lib/acc-operations']
report = {'paths_present': {p: Path(p).exists() or Path(p).is_symlink() for p in paths},
          'runtime_checked': False, 'changes_host': False}
parent = Path('/etc/acc-operations')
try:
    m = parent.lstat()
    if not stat.S_ISDIR(m.st_mode) or m.st_uid != 0 or m.st_mode & 0o022:
        raise ValueError('metadata_parent')
    fd = os.open(parent / 'enrollment.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        m = os.fstat(stream.fileno())
        if not stat.S_ISREG(m.st_mode) or m.st_uid != 0 or m.st_nlink != 1 or m.st_mode & 0o022 or m.st_size > 16384:
            raise ValueError('metadata_file')
        value = json.loads(stream.read(16385))
    report['enrollment_record'] = {k: value.get(k) for k in (
        'source_revision', 'policy_digest', 'receipt_public_key', 'expires_at')}
except Exception:
    report['enrollment_record'] = 'absent_or_requires_review'
print(json.dumps(report))
PY
```

Эти данные не подтверждают активность службы или целостность всего package.
Если есть существующие файлы, сначала точная диагностика, а не install поверх.
Новый проверенный bootstrap поддерживает полноценный metadata-only --inspect,
но он ещё не доставлен на VPS и не должен вызываться из старого checkout.

Дальнейшая установка/активация потребует свежей точной инструкции и разрешения
на действующий срок. Runtime policy отсчитывает свой час от создания; inspection
не обновляет expiry, не обнуляет quota и не заменяет signing key. До подтверждённой
регистрации/активации канал не объявляется постоянным работающим доступом.
