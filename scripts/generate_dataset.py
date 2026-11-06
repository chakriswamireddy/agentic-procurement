import argparse
import json
import random
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "data" / "seed"

DEFAULT_SEED = 42
REFERENCE_DATE = date(2026, 1, 1)
REFERENCE_TIMESTAMP = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
DEFAULT_VALID_UNTIL = REFERENCE_DATE + timedelta(days=90)
TYPICAL_REQUEST_QUANTITY = 100

CATEGORIES = ["electronics", "furniture", "it_hardware", "office_supplies"]
CATEGORY_CODES = {
    "electronics": "ELEC",
    "furniture": "FURN",
    "it_hardware": "IT",
    "office_supplies": "OFF",
}
LOCATIONS = ["IN-TG", "IN-AP", "IN-KA", "IN-MH"]

PRICE_RANGES = {
    "electronics": (2000, 80000),
    "furniture": (1500, 45000),
    "it_hardware": (8000, 75000),
    "office_supplies": (100, 5000),
}

PRODUCT_ADJECTIVES = [
    "Essential",
    "Compact",
    "Premium",
    "Standard",
    "Advanced",
    "Professional",
    "Eco",
    "Executive",
    "Value",
    "Enterprise",
]
PRODUCT_NOUNS = {
    "electronics": ["Monitor", "Router", "Projector", "Camera", "Speaker"],
    "furniture": ["Desk", "Chair", "Cabinet", "Table", "Shelf"],
    "it_hardware": ["Desktop", "Server", "Dock", "Laptop", "Monitor"],
    "office_supplies": ["Paper", "Pen", "Toner", "Folder", "Notebook"],
}

SUPPLIER_PREFIXES = [
    "Apex",
    "Nova",
    "Orbit",
    "Vertex",
    "Crescent",
    "Summit",
    "Pioneer",
    "Meridian",
    "Atlas",
    "Harbor",
    "Cobalt",
    "Evergreen",
    "Sterling",
    "Zenith",
    "Falcon",
    "Ironwood",
    "Bluepeak",
    "Silverline",
    "Northstar",
    "Delta",
]
SUPPLIER_CORES = ["Components", "Systems", "Supplies", "Traders", "Works"]

STATUS_OVERRIDES = {
    "SUP0018": "inactive",
    "SUP0037": "inactive",
    "SUP0083": "inactive",
    "SUP0061": "suspended",
    "SUP0091": "suspended",
}

DUPLICATE_NAMES = {
    "SUP0012": "Nova Components Pvt Ltd",
    "SUP0013": "Nova Components Pvt. Ltd.",
}

MISSING_CERTIFICATIONS = {
    "SUP0007": ["ISO14001"],
    "SUP0029": [],
    "SUP0053": ["ISO14001", "ISO27001"],
    "SUP0074": ["ISO14001"],
    "SUP0096": ["ISO27001"],
}

EXPIRED_QUOTATIONS = {
    11: "2025-12-15",
    123: "2025-11-30",
    245: "2025-12-01",
    351: "2025-10-31",
    489: "2025-12-31",
}
INSUFFICIENT_QUANTITIES = {
    36: 40,
    156: 25,
    278: 10,
    399: 5,
    444: 1,
}
LONG_DELIVERIES = {
    66: 46,
    178: 50,
    299: 60,
    356: 75,
    471: 90,
}
ATTRACTIVE_STATUS_QUOTATIONS = {87, 303, 413}
ANOMALY_QUOTATION = 312
ANOMALY_PRICE = Decimal("1200.00")

MALFORMED_RAW_PAYLOADS = {7, 19, 31, 43, 55}


def supplier_id(n: int) -> str:
    return f"SUP{n:04d}"


def product_id(n: int) -> str:
    return f"PRD{n:04d}"


def quotation_id(n: int) -> str:
    return f"QTN{n:05d}"


def user_id(n: int) -> str:
    return f"USR{n:04d}"


def request_id(n: int) -> str:
    return f"PRQ{n:04d}"


def order_id(n: int) -> str:
    return f"PO{n:04d}"


def payload_id(n: int) -> str:
    return f"RAW{n:04d}"


def money(value: Decimal | int | str) -> str:
    return f"{Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


def iso_date(value: date) -> str:
    return value.isoformat()


def iso_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def supplier_category(n: int) -> str:
    return CATEGORIES[(n - 1) // 25]


def category_index(category: str) -> int:
    return CATEGORIES.index(category)


def product_for_quotation(supplier_n: int, slot: int) -> str:
    ci = (supplier_n - 1) // 25
    supplier_index = (supplier_n - 1) % 25 + 1
    local_product = (supplier_index - 1 + slot) % 50 + 1
    return product_id(ci * 50 + local_product)


def supplier_name(n: int) -> str:
    prefix = SUPPLIER_PREFIXES[(n - 1) % len(SUPPLIER_PREFIXES)]
    core = SUPPLIER_CORES[(n - 1) // len(SUPPLIER_PREFIXES)]
    return f"{prefix} {core} Pvt Ltd"


def build_users() -> list[dict[str, Any]]:
    roles = ["admin"] + ["requester"] * 3 + ["approver"] * 10 + ["auditor"]
    users = []
    for n, role in enumerate(roles, start=1):
        users.append(
            {
                "id": user_id(n),
                "email": f"user{n:04d}@example.test",
                "password_hash": "placeholder-password-hash",
                "role": role,
                "created_at": "2025-12-01T00:00:00Z",
            }
        )
    return users


def build_suppliers() -> list[dict[str, Any]]:
    suppliers = []
    for n in range(1, 101):
        identifier = supplier_id(n)
        name = DUPLICATE_NAMES.get(identifier, supplier_name(n))
        suppliers.append(
            {
                "id": identifier,
                "name": name,
                "category": supplier_category(n),
                "location": LOCATIONS[(n - 1) % len(LOCATIONS)],
                "status": STATUS_OVERRIDES.get(identifier, "active"),
                "created_at": iso_timestamp(
                    REFERENCE_TIMESTAMP - timedelta(days=180) + timedelta(days=n)
                ),
            }
        )
    return suppliers


def build_products(rng: random.Random) -> tuple[list[dict[str, Any]], dict[str, Decimal]]:
    products = []
    reference_prices = {}
    for n in range(1, 201):
        identifier = product_id(n)
        category = CATEGORIES[(n - 1) // 50]
        local_index = (n - 1) % 50
        adjective = PRODUCT_ADJECTIVES[local_index // 5]
        noun = PRODUCT_NOUNS[category][local_index % 5]

        if identifier == "PRD0114":
            reference_price = Decimal("52000.00")
        else:
            low, high = PRICE_RANGES[category]
            reference_price = Decimal(rng.randrange(low, high + 1, 100))

        reference_prices[identifier] = reference_price
        products.append(
            {
                "id": identifier,
                "sku": f"SKU-{CATEGORY_CODES[category]}-{local_index + 1:04d}",
                "name": f"{adjective} {noun}",
                "category": category,
                "attributes_json": {
                    "brand": f"Demo {category.replace('_', ' ').title()}",
                    "unit": "each",
                    "warranty_months": 24 if category in {"electronics", "it_hardware"} else 12,
                },
            }
        )
    return products, reference_prices


def build_quotations(
    rng: random.Random,
    reference_prices: dict[str, Decimal],
) -> list[dict[str, Any]]:
    quotations = []
    for supplier_n in range(1, 101):
        for slot in range(5):
            n = (supplier_n - 1) * 5 + slot + 1
            product = product_for_quotation(supplier_n, slot)
            factor = Decimal(rng.randrange(88, 116)) / 100
            quotations.append(
                {
                    "id": quotation_id(n),
                    "supplier_id": supplier_id(supplier_n),
                    "product_id": product,
                    "unit_price": money(reference_prices[product] * factor),
                    "currency": "INR",
                    "available_quantity": rng.choice([100, 150, 200, 250, 300, 500, 750]),
                    "delivery_days": rng.randint(1, 45),
                    "valid_until": iso_date(DEFAULT_VALID_UNTIL),
                }
            )

    quotations_by_id = {record["id"]: record for record in quotations}
    for n, valid_until in EXPIRED_QUOTATIONS.items():
        quotations_by_id[quotation_id(n)]["valid_until"] = valid_until
    for n, quantity in INSUFFICIENT_QUANTITIES.items():
        quotations_by_id[quotation_id(n)]["available_quantity"] = quantity
    for n, delivery_days in LONG_DELIVERIES.items():
        quotations_by_id[quotation_id(n)]["delivery_days"] = delivery_days
    for n in ATTRACTIVE_STATUS_QUOTATIONS:
        quotation = quotations_by_id[quotation_id(n)]
        base_price = reference_prices[quotation["product_id"]]
        quotation["unit_price"] = money(base_price * Decimal("0.80"))
    quotations_by_id[quotation_id(ANOMALY_QUOTATION)]["unit_price"] = money(ANOMALY_PRICE)

    return quotations


def build_purchase_requests(
    rng: random.Random,
    users: list[dict[str, Any]],
    products: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    requesters = [user["id"] for user in users if user["role"] == "requester"]
    product_ids = [product["id"] for product in products]
    statuses = ["submitted", "approved", "rejected"]
    requests = []
    for n in range(1, 101):
        if n % 10 == 0:
            constraints = {
                "max_delivery_days": 30,
                "required_certifications": ["ISO9001"],
            }
        elif n % 7 == 0:
            constraints = {"max_delivery_days": 45}
        else:
            constraints = {}
        requests.append(
            {
                "id": request_id(n),
                "requester_id": requesters[(n - 1) % len(requesters)],
                "product_id": product_ids[(n * 7) % len(product_ids)],
                "quantity": rng.choice([10, 25, 50, 100, 200, 500]),
                "constraints_json": constraints,
                "status": statuses[(n - 1) % len(statuses)],
                "created_at": iso_timestamp(
                    REFERENCE_TIMESTAMP + timedelta(days=n % 90, hours=n % 8)
                ),
            }
        )
    return requests


def build_purchase_orders(
    rng: random.Random,
    suppliers: list[dict[str, Any]],
    products: list[dict[str, Any]],
    reference_prices: dict[str, Decimal],
) -> list[dict[str, Any]]:
    products_by_category = {
        category: [product for product in products if product["category"] == category]
        for category in CATEGORIES
    }
    statuses = ["created", "fulfilled", "cancelled"]
    orders = []
    for n in range(1, 151):
        supplier = rng.choice(suppliers)
        product = rng.choice(products_by_category[supplier["category"]])
        factor = Decimal(rng.randrange(85, 116)) / 100
        orders.append(
            {
                "id": order_id(n),
                "supplier_id": supplier["id"],
                "product_id": product["id"],
                "quantity": rng.choice([10, 25, 50, 100, 200, 500]),
                "unit_price": money(reference_prices[product["id"]] * factor),
                "status": statuses[(n - 1) % len(statuses)],
                "created_at": iso_timestamp(
                    REFERENCE_TIMESTAMP + timedelta(days=n % 120, hours=n % 24)
                ),
            }
        )
    return orders


def build_supplier_profiles(suppliers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profiles = []
    for n, supplier in enumerate(suppliers, start=1):
        identifier = supplier["id"]
        if identifier in MISSING_CERTIFICATIONS:
            certifications = MISSING_CERTIFICATIONS[identifier]
        else:
            certifications = ["ISO9001", "ISO14001"]
            if supplier["category"] == "it_hardware":
                certifications.append("ISO27001")

        if identifier in MISSING_CERTIFICATIONS:
            risk_level = "low"
            verification_status = "verified"
        else:
            risk_level = "low"
            if n % 11 == 0:
                risk_level = "medium"
            if n % 23 == 0:
                risk_level = "high"

            verification_status = "verified"
            if n % 13 == 0:
                verification_status = "pending"
            if n % 29 == 0:
                verification_status = "failed"

        profiles.append(
            {
                "_id": identifier,
                "supplier_type": supplier["category"],
                "certifications": certifications,
                "regional_registrations": {
                    supplier["location"]: f"REG-{n:04d}",
                },
                "compliance": {
                    "risk_level": risk_level,
                    "verification_status": verification_status,
                },
                "source": {
                    "system": "demo_erp",
                    "last_synced_at": iso_timestamp(REFERENCE_TIMESTAMP),
                },
            }
        )
    return profiles


def build_raw_payloads(
    suppliers: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    profiles_by_id = {profile["_id"]: profile for profile in profiles}
    records = []
    for n in range(1, 61):
        supplier = suppliers[n - 1]
        profile = profiles_by_id[supplier["id"]]
        payload = {
            "supplier_id": supplier["id"],
            "supplier_name": supplier["name"],
            "category": supplier["category"],
            "location": supplier["location"],
            "contact": {
                "email": f"vendor{n:04d}@example.test",
                "phone": f"+91-{n:010d}",
            },
            "certifications": list(profile["certifications"]),
            "regional_registrations": dict(profile["regional_registrations"]),
        }
        record = {
            "payload_id": payload_id(n),
            "source_system": "demo_erp",
            "fetched_at": iso_timestamp(REFERENCE_TIMESTAMP),
            "payload": payload,
            "processing_status": "raw",
        }

        if n == 7:
            payload.pop("supplier_id")
            record["processing_status"] = "failed"
            record["error"] = "missing supplier_id"
        elif n == 19:
            payload["category"] = None
            payload.pop("contact")
            record["processing_status"] = "failed"
            record["error"] = "missing category and contact"
        elif n == 31:
            payload["certifications"] = "ISO9001,ISO14001"
            record["processing_status"] = "failed"
            record["error"] = "certifications must be an array"
        elif n == 43:
            record["payload"] = {
                "supplier_name": supplier["name"],
                "location": supplier["location"],
            }
            record["processing_status"] = "failed"
            record["error"] = "incomplete payload"
        elif n == 55:
            payload["supplier_id"] = "SUP9999"
            record["processing_status"] = "failed"
            record["error"] = "unknown supplier_id"

        records.append(record)
    return records


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_dataset(
    users: list[dict[str, Any]],
    suppliers: list[dict[str, Any]],
    products: list[dict[str, Any]],
    quotations: list[dict[str, Any]],
    requests: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
    raw_payloads: list[dict[str, Any]],
    reference_prices: dict[str, Decimal],
) -> None:
    require(len(users) == 15, "expected 15 users")
    require(len(suppliers) == 100, "expected 100 suppliers")
    require(len(products) == 200, "expected 200 products")
    require(len(quotations) == 500, "expected 500 quotations")
    require(len(requests) == 100, "expected 100 purchase requests")
    require(len(orders) == 150, "expected 150 purchase orders")
    require(len(profiles) == 100, "expected 100 supplier profiles")
    require(len(raw_payloads) == 60, "expected 60 raw payloads")

    user_by_id = {user["id"]: user for user in users}
    supplier_by_id = {supplier["id"]: supplier for supplier in suppliers}
    product_by_id = {product["id"]: product for product in products}
    quotation_by_id = {quotation["id"]: quotation for quotation in quotations}
    profile_by_id = {profile["_id"]: profile for profile in profiles}

    require(len(supplier_by_id) == 100, "duplicate supplier IDs")
    require(len(product_by_id) == 200, "duplicate product IDs")
    require(len(quotation_by_id) == 500, "duplicate quotation IDs")
    require(len(profile_by_id) == 100, "duplicate profile IDs")

    roles = [user["role"] for user in users]
    require(roles.count("admin") == 1, "expected one admin")
    require(roles.count("requester") == 3, "expected three requesters")
    require(roles.count("approver") == 10, "expected ten approvers")
    require(roles.count("auditor") == 1, "expected one auditor")

    for supplier in suppliers:
        require(supplier["category"] in CATEGORIES, f"bad category: {supplier['id']}")
        require(supplier["location"] in LOCATIONS, f"bad location: {supplier['id']}")
        require(
            supplier["status"] in {"active", "inactive", "suspended"},
            f"bad status: {supplier['id']}",
        )

    for product in products:
        require(product["category"] in CATEGORIES, f"bad product category: {product['id']}")
        require(reference_prices[product["id"]] > 0, f"bad price: {product['id']}")

    for quotation in quotations:
        supplier = supplier_by_id.get(quotation["supplier_id"])
        product = product_by_id.get(quotation["product_id"])
        require(supplier is not None, f"unknown supplier: {quotation['id']}")
        require(product is not None, f"unknown product: {quotation['id']}")
        require(
            supplier["category"] == product["category"],
            f"category mismatch: {quotation['id']}",
        )
        require(quotation["currency"] == "INR", f"bad currency: {quotation['id']}")
        require(quotation["available_quantity"] > 0, f"bad quantity: {quotation['id']}")
        require(quotation["delivery_days"] > 0, f"bad delivery: {quotation['id']}")

    for request in requests:
        require(request["requester_id"] in user_by_id, "invalid requester reference")
        require(request["product_id"] in product_by_id, f"bad request product: {request['id']}")

    for order in orders:
        require(order["supplier_id"] in supplier_by_id, f"bad order supplier: {order['id']}")
        require(order["product_id"] in product_by_id, f"bad order product: {order['id']}")

    for n, expected_date in EXPIRED_QUOTATIONS.items():
        require(
            quotation_by_id[quotation_id(n)]["valid_until"] == expected_date,
            f"expired edge mismatch: {quotation_id(n)}",
        )
        require(
            date.fromisoformat(expected_date) < REFERENCE_DATE,
            f"expired edge is not expired: {quotation_id(n)}",
        )
    for n, quantity in INSUFFICIENT_QUANTITIES.items():
        require(
            quotation_by_id[quotation_id(n)]["available_quantity"] == quantity,
            f"quantity edge mismatch: {quotation_id(n)}",
        )
        require(quantity < TYPICAL_REQUEST_QUANTITY, f"quantity edge too high: {quotation_id(n)}")
    for n, delivery_days in LONG_DELIVERIES.items():
        require(
            quotation_by_id[quotation_id(n)]["delivery_days"] == delivery_days,
            f"delivery edge mismatch: {quotation_id(n)}",
        )
        require(delivery_days > 45, f"delivery edge too low: {quotation_id(n)}")

    for n in ATTRACTIVE_STATUS_QUOTATIONS:
        quotation = quotation_by_id[quotation_id(n)]
        supplier = supplier_by_id[quotation["supplier_id"]]
        require(
            supplier["status"] in {"inactive", "suspended"},
            f"status edge is active: {supplier['id']}",
        )
        expected = money(reference_prices[quotation["product_id"]] * Decimal("0.80"))
        require(quotation["unit_price"] == expected, f"price edge mismatch: {quotation['id']}")

    anomaly = quotation_by_id[quotation_id(ANOMALY_QUOTATION)]
    require(anomaly["unit_price"] == money(ANOMALY_PRICE), "anomaly price mismatch")
    require(anomaly["supplier_id"] == "SUP0063", "anomaly supplier mismatch")
    require(anomaly["product_id"] == "PRD0114", "anomaly product mismatch")

    require(supplier_by_id["SUP0012"]["name"] == DUPLICATE_NAMES["SUP0012"], "duplicate name")
    require(supplier_by_id["SUP0013"]["name"] == DUPLICATE_NAMES["SUP0013"], "duplicate name")

    for identifier, expected_certifications in MISSING_CERTIFICATIONS.items():
        actual = profile_by_id[identifier]["certifications"]
        require(actual == expected_certifications, f"certification edge mismatch: {identifier}")
        require("ISO9001" not in actual, f"certification edge still has ISO9001: {identifier}")

    for profile in profiles:
        require(profile["_id"] in supplier_by_id, f"orphan profile: {profile['_id']}")
        require(
            profile["supplier_type"] == supplier_by_id[profile["_id"]]["category"],
            f"profile category mismatch: {profile['_id']}",
        )

    failed_payloads = {
        record["payload_id"] for record in raw_payloads if record["processing_status"] == "failed"
    }
    expected_failed = {payload_id(n) for n in MALFORMED_RAW_PAYLOADS}
    require(failed_payloads == expected_failed, "raw payload failure set mismatch")


def json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def jsonl_text(records: list[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )


def build_dataset(seed: int) -> dict[str, str]:
    rng = random.Random(seed)

    users = build_users()
    suppliers = build_suppliers()
    products, reference_prices = build_products(rng)
    quotations = build_quotations(rng, reference_prices)
    requests = build_purchase_requests(rng, users, products)
    orders = build_purchase_orders(rng, suppliers, products, reference_prices)
    profiles = build_supplier_profiles(suppliers)
    raw_payloads = build_raw_payloads(suppliers, profiles)

    validate_dataset(
        users,
        suppliers,
        products,
        quotations,
        requests,
        orders,
        profiles,
        raw_payloads,
        reference_prices,
    )

    return {
        "users.json": json_text(users),
        "suppliers.json": json_text(suppliers),
        "products.json": json_text(products),
        "quotations.json": json_text(quotations),
        "purchase_requests.json": json_text(requests),
        "purchase_orders.json": json_text(orders),
        "supplier_profiles.jsonl": jsonl_text(profiles),
        "raw_supplier_payloads.jsonl": jsonl_text(raw_payloads),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic seed data.")
    parser.add_argument("--check", action="store_true", help="compare generated data with files")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed override")
    args = parser.parse_args()

    files = build_dataset(args.seed)

    if args.check:
        problems = []
        for name, content in files.items():
            path = SEED_DIR / name
            if not path.exists():
                problems.append(f"missing: {name}")
            elif path.read_text(encoding="utf-8") != content:
                problems.append(f"drift: {name}")
        if problems:
            print("dataset check failed")
            for problem in problems:
                print(f"  {problem}")
            return 1
        print(f"dataset check ok ({len(files)} files)")
        return 0

    SEED_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (SEED_DIR / name).write_text(content, encoding="utf-8")
    print(f"generated {len(files)} files in {SEED_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
