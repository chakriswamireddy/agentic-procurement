import json
import os
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "data" / "seed"
SCHEMA_DIR = ROOT / "scripts" / "sql"
URL_KEYS = ("DATABASE_URL",)
SECRET_MARKERS = ("PASSWORD", "SECRET", "TOKEN", "API_KEY", "APIKEY")


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


def error_text(exc: BaseException) -> str:
    return " ".join(str(exc).split()) or exc.__class__.__name__


def database_url() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("DATABASE_URL is not set")
    return strip_driver(value)


def read_json(name: str) -> list[dict[str, Any]]:
    path = SEED_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(name: str) -> list[dict[str, Any]]:
    path = SEED_DIR / name
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{name}:{line_number}: invalid JSON") from exc
    return records


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def existing_ids(cursor: psycopg.Cursor[Any], table: str) -> set[str]:
    cursor.execute(f"SELECT id FROM {table}")
    return {row[0] for row in cursor.fetchall()}


def change_counts(rows: list[dict[str, Any]], existing: set[str]) -> tuple[int, int]:
    inserted = sum(1 for row in rows if row["id"] not in existing)
    return inserted, len(rows) - inserted


def seed_users(cursor: psycopg.Cursor[Any], rows: list[dict[str, Any]]) -> tuple[int, int]:
    existing = existing_ids(cursor, "users")
    cursor.executemany(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            email = EXCLUDED.email,
            password_hash = EXCLUDED.password_hash,
            role = EXCLUDED.role,
            is_active = EXCLUDED.is_active,
            created_at = EXCLUDED.created_at
        """,
        [
            (
                row["id"],
                row["email"],
                row["password_hash"],
                row["role"],
                row.get("is_active", True),
                parse_timestamp(row["created_at"]),
            )
            for row in rows
        ],
    )
    return change_counts(rows, existing)


def seed_suppliers(cursor: psycopg.Cursor[Any], rows: list[dict[str, Any]]) -> tuple[int, int]:
    existing = existing_ids(cursor, "suppliers")
    cursor.executemany(
        """
        INSERT INTO suppliers (id, name, category, location, status, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            category = EXCLUDED.category,
            location = EXCLUDED.location,
            status = EXCLUDED.status,
            created_at = EXCLUDED.created_at
        """,
        [
            (
                row["id"],
                row["name"],
                row["category"],
                row["location"],
                row["status"],
                parse_timestamp(row["created_at"]),
            )
            for row in rows
        ],
    )
    return change_counts(rows, existing)


def seed_products(cursor: psycopg.Cursor[Any], rows: list[dict[str, Any]]) -> tuple[int, int]:
    existing = existing_ids(cursor, "products")
    cursor.executemany(
        """
        INSERT INTO products (id, sku, name, category, attributes_json)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            sku = EXCLUDED.sku,
            name = EXCLUDED.name,
            category = EXCLUDED.category,
            attributes_json = EXCLUDED.attributes_json
        """,
        [
            (
                row["id"],
                row["sku"],
                row["name"],
                row["category"],
                Jsonb(row["attributes_json"]),
            )
            for row in rows
        ],
    )
    return change_counts(rows, existing)


def seed_quotations(cursor: psycopg.Cursor[Any], rows: list[dict[str, Any]]) -> tuple[int, int]:
    existing = existing_ids(cursor, "quotations")
    cursor.executemany(
        """
        INSERT INTO quotations (
            id,
            supplier_id,
            product_id,
            unit_price,
            currency,
            available_quantity,
            delivery_days,
            valid_until
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            supplier_id = EXCLUDED.supplier_id,
            product_id = EXCLUDED.product_id,
            unit_price = EXCLUDED.unit_price,
            currency = EXCLUDED.currency,
            available_quantity = EXCLUDED.available_quantity,
            delivery_days = EXCLUDED.delivery_days,
            valid_until = EXCLUDED.valid_until
        """,
        [
            (
                row["id"],
                row["supplier_id"],
                row["product_id"],
                Decimal(row["unit_price"]),
                row["currency"],
                row["available_quantity"],
                row["delivery_days"],
                date.fromisoformat(row["valid_until"]),
            )
            for row in rows
        ],
    )
    return change_counts(rows, existing)


def seed_procurement_requests(
    cursor: psycopg.Cursor[Any],
    rows: list[dict[str, Any]],
) -> tuple[int, int]:
    existing = existing_ids(cursor, "procurement_requests")
    cursor.executemany(
        """
        INSERT INTO procurement_requests (
            id,
            requester_id,
            product_id,
            quantity,
            constraints_json,
            status,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            requester_id = EXCLUDED.requester_id,
            product_id = EXCLUDED.product_id,
            quantity = EXCLUDED.quantity,
            constraints_json = EXCLUDED.constraints_json,
            status = EXCLUDED.status,
            created_at = EXCLUDED.created_at
        """,
        [
            (
                row["id"],
                row["requester_id"],
                row["product_id"],
                row["quantity"],
                Jsonb(row["constraints_json"]),
                row["status"],
                parse_timestamp(row["created_at"]),
            )
            for row in rows
        ],
    )
    return change_counts(rows, existing)


def seed_purchase_orders(
    cursor: psycopg.Cursor[Any],
    rows: list[dict[str, Any]],
) -> tuple[int, int]:
    existing = existing_ids(cursor, "purchase_orders")
    cursor.executemany(
        """
        INSERT INTO purchase_orders (
            id,
            supplier_id,
            product_id,
            quantity,
            unit_price,
            status,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            supplier_id = EXCLUDED.supplier_id,
            product_id = EXCLUDED.product_id,
            quantity = EXCLUDED.quantity,
            unit_price = EXCLUDED.unit_price,
            status = EXCLUDED.status,
            created_at = EXCLUDED.created_at
        """,
        [
            (
                row["id"],
                row["supplier_id"],
                row["product_id"],
                row["quantity"],
                Decimal(row["unit_price"]),
                row["status"],
                parse_timestamp(row["created_at"]),
            )
            for row in rows
        ],
    )
    return change_counts(rows, existing)


def apply_schema(dsn: str) -> None:
    schema_files = sorted(SCHEMA_DIR.glob("*.sql"))
    if not schema_files:
        raise RuntimeError(f"no schema files found in {SCHEMA_DIR}")
    with psycopg.connect(dsn, autocommit=True) as connection:
        for schema_path in schema_files:
            connection.execute(schema_path.read_text(encoding="utf-8"))


def main() -> int:
    try:
        load_dotenv(ROOT / ".env")
        dsn = database_url()
        apply_schema(dsn)

        users = read_json("users.json")
        suppliers = read_json("suppliers.json")
        products = read_json("products.json")
        quotations = read_json("quotations.json")
        requests = read_json("purchase_requests.json")
        orders = read_json("purchase_orders.json")

        reports = []
        with psycopg.connect(dsn) as connection:
            with connection.cursor() as cursor:
                reports.append(("users", *seed_users(cursor, users)))
                reports.append(("suppliers", *seed_suppliers(cursor, suppliers)))
                reports.append(("products", *seed_products(cursor, products)))
                reports.append(("quotations", *seed_quotations(cursor, quotations)))
                reports.append(
                    ("procurement_requests", *seed_procurement_requests(cursor, requests))
                )
                reports.append(("purchase_orders", *seed_purchase_orders(cursor, orders)))

        for table, inserted, updated in reports:
            print(f"{table}: {inserted} inserted, {updated} updated")
        print("postgres seed complete")

        # Invalidate supplier cache in Redis by bumping version (Phase 6)
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            import redis
            r = redis.from_url(redis_url, socket_timeout=1.0)
            new_ver = r.incr("suppliers:cache_version")
            print(f"redis supplier cache invalidated (cache_version={new_ver})")
            r.close()
        except Exception:
            pass

        return 0
    except Exception as exc:
        print(f"postgres seed failed: {redact(error_text(exc))}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
