import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient, ReplaceOne

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "data" / "seed"
URL_KEYS = ("MONGODB_URL",)
SECRET_MARKERS = ("PASSWORD", "SECRET", "TOKEN", "API_KEY", "APIKEY")
ALLOWED_PROCESSING_STATUSES = {"raw", "parsed", "failed"}
FORBIDDEN_PROFILE_FIELDS = {"name", "status", "category"}


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


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


def validate_profiles(
    suppliers: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
) -> None:
    supplier_ids = {supplier["id"] for supplier in suppliers}
    profile_ids = [profile.get("_id") for profile in profiles]

    if any(identifier is None for identifier in profile_ids):
        raise ValueError("every supplier profile must have an _id")

    duplicate_ids = sorted(
        {identifier for identifier in profile_ids if profile_ids.count(identifier) > 1}
    )
    if duplicate_ids:
        raise ValueError(f"duplicate supplier profile IDs: {', '.join(duplicate_ids)}")

    unknown_ids = sorted(set(profile_ids) - supplier_ids)
    if unknown_ids:
        raise ValueError(f"unknown supplier profile IDs: {', '.join(unknown_ids)}")

    missing_ids = sorted(supplier_ids - set(profile_ids))
    if missing_ids:
        raise ValueError(f"missing supplier profile IDs: {', '.join(missing_ids)}")

    for profile in profiles:
        forbidden = sorted(FORBIDDEN_PROFILE_FIELDS & set(profile))
        if forbidden:
            raise ValueError(
                f"profile {profile['_id']} contains PostgreSQL-owned fields: "
                f"{', '.join(forbidden)}"
            )


def validate_raw_payloads(raw_payloads: list[dict[str, Any]]) -> None:
    payload_ids = [record.get("payload_id") for record in raw_payloads]
    if any(identifier is None for identifier in payload_ids):
        raise ValueError("every raw payload must have a payload_id")

    duplicate_ids = sorted(
        {identifier for identifier in payload_ids if payload_ids.count(identifier) > 1}
    )
    if duplicate_ids:
        raise ValueError(f"duplicate raw payload IDs: {', '.join(duplicate_ids)}")

    for record in raw_payloads:
        missing = {
            "source_system",
            "fetched_at",
            "payload",
            "processing_status",
        } - set(record)
        if missing:
            raise ValueError(
                f"raw payload {record['payload_id']} is missing: {', '.join(sorted(missing))}"
            )
        status = record["processing_status"]
        if status not in ALLOWED_PROCESSING_STATUSES:
            raise ValueError(
                f"raw payload {record['payload_id']} has invalid status: {status}"
            )
        if status == "failed" and not record.get("error"):
            raise ValueError(f"failed raw payload {record['payload_id']} has no error")


def upsert_documents(collection: Any, documents: list[dict[str, Any]], key: str) -> Any:
    operations = [
        ReplaceOne({key: document[key]}, document, upsert=True) for document in documents
    ]
    return collection.bulk_write(operations, ordered=False)


def main() -> int:
    try:
        load_dotenv(ROOT / ".env")
        mongodb_url = require_env("MONGODB_URL")
        database_name = require_env("MONGODB_DB")

        suppliers = read_json("suppliers.json")
        profiles = read_jsonl("supplier_profiles.jsonl")
        raw_payloads = read_jsonl("raw_supplier_payloads.jsonl")

        validate_profiles(suppliers, profiles)
        validate_raw_payloads(raw_payloads)

        with MongoClient(mongodb_url, serverSelectionTimeoutMS=5000) as client:
            database = client[database_name]
            profile_collection = database["supplier_profiles"]
            raw_collection = database["raw_supplier_payloads"]

            profile_collection.create_index([("compliance.risk_level", ASCENDING)])
            profile_collection.create_index([("certifications", ASCENDING)])
            profile_collection.create_index([("source.system", ASCENDING)])
            raw_collection.create_index([("payload_id", ASCENDING)], unique=True)

            profile_result = upsert_documents(profile_collection, profiles, "_id")
            raw_result = upsert_documents(raw_collection, raw_payloads, "payload_id")

        print(
            "supplier_profiles: "
            f"{profile_result.upserted_count} inserted, "
            f"{profile_result.modified_count} updated"
        )
        print(
            "raw_supplier_payloads: "
            f"{raw_result.upserted_count} inserted, "
            f"{raw_result.modified_count} updated"
        )
        print("mongodb seed complete")
        return 0
    except Exception as exc:
        print(f"mongodb seed failed: {redact(error_text(exc))}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
