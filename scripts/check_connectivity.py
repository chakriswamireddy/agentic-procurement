import os
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

import psycopg
from dotenv import load_dotenv
from pymongo import MongoClient
from qdrant_client import QdrantClient
from redis import Redis

ROOT = Path(__file__).resolve().parents[1]
URL_KEYS = ("DATABASE_URL", "MONGODB_URL", "REDIS_URL", "QDRANT_URL")
SECRET_MARKERS = ("PASSWORD", "SECRET", "TOKEN", "API_KEY", "APIKEY")
TIMEOUT_SECONDS = 3


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def strip_driver(url: str) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme.split("+", 1)[0]
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))


def redact(message: str) -> str:
    for key in URL_KEYS:
        value = os.getenv(key)
        if value:
            message = message.replace(value, "<redacted-url>")

    secrets = []
    for key, value in os.environ.items():
        upper_key = key.upper()
        if not value:
            continue
        if any(marker in upper_key for marker in SECRET_MARKERS):
            secrets.append(value)
        if upper_key in URL_KEYS:
            try:
                password = urlsplit(value).password
            except ValueError:
                password = None
            if password:
                secrets.append(password)
                secrets.append(unquote(password))

    for secret in sorted(set(secrets), key=len, reverse=True):
        if len(secret) >= 4:
            message = message.replace(secret, "***")

    message = re.sub(
        r"(?i)\b(password|passwd|pwd|token|secret|api[_-]?key)=([^&\s,;]+)",
        r"\1=***",
        message,
    )
    return re.sub(r"://[^/@\s]+@", "://***@", message)


def error_message(exc: BaseException) -> str:
    message = " ".join(str(exc).split()) or exc.__class__.__name__
    return redact(message)


def check_postgres() -> str:
    dsn = strip_driver(require_env("DATABASE_URL"))
    with psycopg.connect(
        dsn,
        connect_timeout=TIMEOUT_SECONDS,
        options=f"-c statement_timeout={TIMEOUT_SECONDS * 1000}",
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('suppliers')")
            if cursor.fetchone()[0] is None:
                return "0 suppliers"
            cursor.execute("SELECT count(*) FROM suppliers")
            count = cursor.fetchone()[0]
    return f"{count} suppliers"


def check_mongodb() -> str:
    url = require_env("MONGODB_URL")
    database = require_env("MONGODB_DB")
    client = MongoClient(
        url,
        serverSelectionTimeoutMS=TIMEOUT_SECONDS * 1000,
        connectTimeoutMS=TIMEOUT_SECONDS * 1000,
        socketTimeoutMS=TIMEOUT_SECONDS * 1000,
    )
    try:
        count = client[database]["supplier_profiles"].count_documents(
            {}, maxTimeMS=TIMEOUT_SECONDS * 1000
        )
    finally:
        client.close()
    return f"{count} profiles"


def check_redis() -> str:
    url = require_env("REDIS_URL")
    client = Redis.from_url(
        url,
        socket_connect_timeout=TIMEOUT_SECONDS,
        socket_timeout=TIMEOUT_SECONDS,
    )
    try:
        client.ping()
    finally:
        client.close()
    return "pong"


def check_qdrant() -> str:
    url = require_env("QDRANT_URL")
    client = QdrantClient(url=url, timeout=TIMEOUT_SECONDS)
    try:
        count = len(client.get_collections().collections)
    finally:
        client.close()
    return f"{count} collections"


CHECKS = (
    ("postgres", check_postgres),
    ("mongodb", check_mongodb),
    ("redis", check_redis),
    ("qdrant", check_qdrant),
)


def main() -> int:
    load_dotenv(ROOT / ".env")

    failed = False
    for name, check in CHECKS:
        try:
            detail = check()
        except Exception as exc:
            failed = True
            print(f"{name}: failed ({error_message(exc)})")
        else:
            print(f"{name}: ok ({detail})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
