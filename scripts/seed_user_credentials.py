#!/usr/bin/env python3
"""Seed Argon2 password hashes for demo users (Phase 5.1).

Reads data/seed/users.json, hashes a demo password, and upserts
password_hash + is_active. Prints emails and roles only — never passwords.

Refuses to run when APP_ENV=production unless SEED_ALLOW_PRODUCTION=1 and a
secure password source is provided via DEMO_USER_PASSWORD.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

# Local-only default; production must set DEMO_USER_PASSWORD explicitly.
LOCAL_DEFAULT_PASSWORD = "Password123!"
MIN_PASSWORD_LENGTH = 12


def main() -> int:
    app_env = os.getenv("APP_ENV", "development").lower()
    password = os.getenv("DEMO_USER_PASSWORD") or LOCAL_DEFAULT_PASSWORD

    if app_env == "production":
        if os.getenv("SEED_ALLOW_PRODUCTION") != "1":
            print(
                "refusing to seed credentials in production without "
                "SEED_ALLOW_PRODUCTION=1 and DEMO_USER_PASSWORD",
                file=sys.stderr,
            )
            return 2
        if not os.getenv("DEMO_USER_PASSWORD"):
            print(
                "DEMO_USER_PASSWORD must be set in production",
                file=sys.stderr,
            )
            return 2

    if len(password) < MIN_PASSWORD_LENGTH:
        print(
            f"demo password must be at least {MIN_PASSWORD_LENGTH} characters",
            file=sys.stderr,
        )
        return 2

    from app.core.config import get_settings
    from app.core.security import hash_password
    from app.database.postgres.engine import init_engine
    from app.database.postgres.session import get_session_factory, init_session_factory

    settings = get_settings()
    users_path = ROOT / "data" / "seed" / "users.json"
    rows = json.loads(users_path.read_text(encoding="utf-8"))

    password_hash = hash_password(password)
    engine = init_engine(settings)
    init_session_factory(engine)

    import asyncio

    async def _upsert() -> None:
        from sqlalchemy import text

        factory = get_session_factory()
        async with factory() as session:
            for row in rows:
                await session.execute(
                    text(
                        """
                        INSERT INTO users (id, email, password_hash, role, is_active)
                        VALUES (:id, :email, :hash, :role, TRUE)
                        ON CONFLICT (id) DO UPDATE SET
                            password_hash = EXCLUDED.password_hash,
                            is_active = TRUE
                        """
                    ),
                    {
                        "id": row["id"],
                        "email": row["email"],
                        "hash": password_hash,
                        "role": row["role"],
                    },
                )
            await session.commit()
        await engine.dispose()

    asyncio.run(_upsert())

    for row in rows:
        print(f"{row['id']}\t{row['email']}\t{row['role']}")
    print(f"seeded {len(rows)} users (password not shown)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
