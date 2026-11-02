"""Create a private local .env without overwriting existing configuration."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
destination = root / ".env"
content = (
    (root / ".env.example")
    .read_text()
    .replace("replace-with-a-local-password", secrets.token_urlsafe(32))
)
try:
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print("Existing .env preserved.")
else:
    with os.fdopen(fd, "w") as stream:
        stream.write(content)
    print("Created private .env with a random local database password.")
