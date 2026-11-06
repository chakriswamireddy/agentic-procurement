import hashlib
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pytest
from pymongo import MongoClient
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from scripts.generate_dataset import (
    ATTRACTIVE_STATUS_QUOTATIONS,
    DEFAULT_SEED,
    EXPIRED_QUOTATIONS,
    INSUFFICIENT_QUANTITIES,
    LONG_DELIVERIES,
    SEED_DIR,
    build_dataset,
    quotation_id,
)
from scripts.seed_postgres import strip_driver

ROOT = Path(__file__).resolve().parents[2]
POSTGRES_TABLES = (
    "users",
    "suppliers",
    "products",
    "quotations",
    "procurement_requests",
    "purchase_orders",
)


def read_json(name: str) -> list[dict[str, Any]]:
    return json.loads((SEED_DIR / name).read_text(encoding="utf-8"))


def postgres_dsn() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL is not set")
    return strip_driver(value)


def postgres_counts() -> dict[str, int]:
    counts = {}
    with psycopg.connect(postgres_dsn()) as connection:
        with connection.cursor() as cursor:
            for table in POSTGRES_TABLES:
                cursor.execute(f"SELECT count(*) FROM {table}")
                counts[table] = cursor.fetchone()[0]
    return counts


def test_generator_is_deterministic() -> None:
    first = build_dataset(DEFAULT_SEED)
    second = build_dataset(DEFAULT_SEED)

    first_hashes = {
        name: hashlib.sha256(content.encode("utf-8")).hexdigest()
        for name, content in first.items()
    }
    second_hashes = {
        name: hashlib.sha256(content.encode("utf-8")).hexdigest()
        for name, content in second.items()
    }

    assert first_hashes == second_hashes
    assert len(first_hashes) == 8


def test_referential_integrity() -> None:
    suppliers = read_json("suppliers.json")
    products = read_json("products.json")
    quotations = read_json("quotations.json")
    requests = read_json("purchase_requests.json")
    orders = read_json("purchase_orders.json")
    users = read_json("users.json")

    supplier_ids = {supplier["id"] for supplier in suppliers}
    product_ids = {product["id"] for product in products}
    user_ids = {user["id"] for user in users}

    assert len(quotations) == 500
    for quotation in quotations:
        assert quotation["supplier_id"] in supplier_ids
        assert quotation["product_id"] in product_ids

    for request in requests:
        assert request["requester_id"] in user_ids
        assert request["product_id"] in product_ids

    for order in orders:
        assert order["supplier_id"] in supplier_ids
        assert order["product_id"] in product_ids


def test_edge_cases_present() -> None:
    suppliers = read_json("suppliers.json")
    quotations = read_json("quotations.json")
    quotations_by_id = {quotation["id"]: quotation for quotation in quotations}

    expired = {
        identifier
        for identifier, quotation in quotations_by_id.items()
        if date.fromisoformat(quotation["valid_until"]) < date(2026, 1, 1)
    }
    insufficient = {
        identifier
        for identifier, quotation in quotations_by_id.items()
        if quotation["available_quantity"] < 100
    }
    long_delivery = {
        identifier
        for identifier, quotation in quotations_by_id.items()
        if quotation["delivery_days"] > 45
    }
    inactive_supplier_ids = {
        supplier["id"] for supplier in suppliers if supplier["status"] == "inactive"
    }

    assert expired == {quotation_id(n) for n in EXPIRED_QUOTATIONS}
    assert insufficient == {quotation_id(n) for n in INSUFFICIENT_QUANTITIES}
    assert long_delivery == {quotation_id(n) for n in LONG_DELIVERIES}
    assert inactive_supplier_ids == {"SUP0018", "SUP0037", "SUP0083"}
    assert {
        quotation["supplier_id"]
        for identifier in ATTRACTIVE_STATUS_QUOTATIONS
        for quotation in [quotations_by_id[quotation_id(identifier)]]
    } <= inactive_supplier_ids | {"SUP0061", "SUP0091"}


@pytest.mark.integration
def test_postgres_seed_idempotent(seeded_postgres: None) -> None:
    before = postgres_counts()

    from backend.tests.conftest import run_script

    run_script("seed_postgres.py")
    after = postgres_counts()

    assert before == after
    assert all(count > 0 for count in after.values())


@pytest.mark.integration
def test_postgres_money_is_decimal(seeded_postgres: None) -> None:
    with psycopg.connect(postgres_dsn()) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT unit_price FROM quotations ORDER BY id LIMIT 1")
            unit_price = cursor.fetchone()[0]

    assert isinstance(unit_price, Decimal)
    assert not isinstance(unit_price, float)


@pytest.mark.integration
def test_mongo_profiles_link_to_postgres(seeded_postgres: None, seeded_mongodb: None) -> None:
    mongodb_url = os.getenv("MONGODB_URL")
    mongodb_db = os.getenv("MONGODB_DB")
    if not mongodb_url or not mongodb_db:
        pytest.skip("MONGODB_URL or MONGODB_DB is not set")

    with psycopg.connect(postgres_dsn()) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM suppliers")
            supplier_ids = {row[0] for row in cursor.fetchall()}

    with MongoClient(mongodb_url, serverSelectionTimeoutMS=5000) as client:
        profile_ids = set(client[mongodb_db]["supplier_profiles"].distinct("_id"))

    assert profile_ids
    assert profile_ids <= supplier_ids


@pytest.mark.integration
def test_qdrant_ingestion_idempotent(ingested_qdrant: None) -> None:
    from backend.tests.conftest import run_script

    qdrant_url = os.getenv("QDRANT_URL")
    if not qdrant_url:
        pytest.skip("QDRANT_URL is not set")
    collection_name = os.getenv("QDRANT_COLLECTION", "policy_chunks")

    client = QdrantClient(url=qdrant_url)
    try:
        before = client.count(collection_name=collection_name, exact=True).count
        run_script("ingest_documents.py")
        after = client.count(collection_name=collection_name, exact=True).count
    finally:
        client.close()

    assert before > 0
    assert after == before


@pytest.mark.integration
def test_obsolete_documents_are_filterable(ingested_qdrant: None) -> None:
    qdrant_url = os.getenv("QDRANT_URL")
    if not qdrant_url:
        pytest.skip("QDRANT_URL is not set")
    collection_name = os.getenv("QDRANT_COLLECTION", "policy_chunks")

    client = QdrantClient(url=qdrant_url)
    try:
        obsolete_points, _ = client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="status", match=MatchValue(value="obsolete"))]
            ),
            limit=200,
            with_payload=True,
        )
        active_points, _ = client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="status", match=MatchValue(value="active"))]
            ),
            limit=200,
            with_payload=True,
        )
        excluded, _ = client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="document_id", match=MatchValue(value="POL-011")),
                    FieldCondition(key="status", match=MatchValue(value="active")),
                ]
            ),
            limit=200,
            with_payload=True,
        )
    finally:
        client.close()

    assert obsolete_points
    assert {point.payload["document_id"] for point in obsolete_points} == {"POL-011"}
    assert all(point.payload["status"] == "active" for point in active_points)
    assert "POL-011" not in {point.payload["document_id"] for point in active_points}
    assert excluded == []
