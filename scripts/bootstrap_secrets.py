"""Generate cloud-local synthetic secrets without printing their values."""
import json
import os
from pathlib import Path
import secrets

root = Path(".runtime/secrets")
root.mkdir(parents=True, exist_ok=True, mode=0o700)
values = {"db_admin_password": secrets.token_urlsafe(32), "backup_key": secrets.token_hex(32), "db_password": secrets.token_urlsafe(32), "redis_password": secrets.token_urlsafe(32),
          "identities.json": json.dumps({r: secrets.token_urlsafe(32) for r in ("owner", "operator", "agent")})}
for name, value in values.items():
    fd = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as file:
        file.write(value)
print("Synthetic secret files created; values were not printed.")
