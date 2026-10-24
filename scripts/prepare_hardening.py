"""Create only missing cloud synthetic runtime credentials/directories; never overwrite."""
import os
from pathlib import Path
import secrets

for name in ('broker-socket', 'runtime-ledger', 'secrets'):
    Path('.runtime', name).mkdir(parents=True, mode=0o700, exist_ok=True)
for name in ('db_runtime_password', 'broker_token'):
    path = Path('.runtime/secrets') / name
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        continue
    with os.fdopen(fd, 'w') as file:
        file.write(secrets.token_urlsafe(32))
print('Cloud runtime directories/credentials prepared; no values printed.')
