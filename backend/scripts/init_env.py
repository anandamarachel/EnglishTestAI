"""Create a private local .env, or add newly required secrets to an existing one.

Existing values are never overwritten.
"""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
destination = root / ".env"
# Generated per developer; never shared or committed.
GENERATED = {
    "POSTGRES_PASSWORD": ("replace-with-a-local-password", lambda: secrets.token_urlsafe(32)),
    "JWT_SECRET": (
        "replace-with-a-random-secret-of-at-least-32-characters",
        lambda: secrets.token_urlsafe(48),
    ),
}

content = (root / ".env.example").read_text()
for placeholder, generate in GENERATED.values():
    content = content.replace(placeholder, generate())

try:
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    existing = destination.read_text()
    defined = {
        line.split("=", 1)[0].strip()
        for line in existing.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    missing = [key for key in GENERATED if key not in defined]
    if missing:
        with destination.open("a") as stream:
            if not existing.endswith("\n"):
                stream.write("\n")
            for key in missing:
                stream.write(f"{key}={GENERATED[key][1]()}\n")
        print(f"Existing .env preserved; added missing {', '.join(missing)}.")
    else:
        print("Existing .env preserved.")
else:
    with os.fdopen(fd, "w") as stream:
        stream.write(content)
    print("Created private .env with random local secrets.")
