# ADR 0001: Deterministic dataset design

- **Status:** Accepted
- **Date:** 2026-10-31
- **Phase:** 0
- **Decision owner:** Data foundation

## Context

The application must be developed and tested against data that is stable, reproducible, and contains deliberate edge cases. Random data generated afresh on every run would make diffs noisy, break retrieval and workflow tests, and hide eligibility bugs.

This ADR fixes the identifier formats, counts, reference values, and exact edge-case records before the generator is written. The generator in Step 0.5 must implement this document rather than inventing its own values.

## Decision

All seed data is synthetic. No real supplier, person, contact, or confidential information is used. Generation is deterministic: the same generator version must produce byte-identical files on every run.

### Reference date and formatting

- **Reference date:** `2026-01-01`.
- All relative dates are calculated from this fixed date, never from the system clock.
- Dates use ISO `YYYY-MM-DD`. Timestamps use ISO 8601 UTC, for example `2026-01-01T10:00:00Z`.
- Money is serialized as a decimal string with exactly two fractional digits, for example `"1250.00"`.
- All quotations use currency `INR`. PostgreSQL stores `unit_price` as `NUMERIC(12,2)`.

### Identifier formats and record counts

| Entity | ID format | Range | Count |
|---|---|---|---:|
| Supplier | `SUP` + 4 digits | `SUP0001`–`SUP0100` | 100 |
| Product | `PRD` + 4 digits | `PRD0001`–`PRD0200` | 200 |
| Quotation | `QTN` + 5 digits | `QTN00001`–`QTN00500` | 500 |
| User | `USR` + 4 digits | `USR0001`–`USR0015` | 15 |
| Purchase request | `PRQ` + 4 digits | `PRQ0001`–`PRQ0100` | 100 |
| Purchase order | `PO` + 4 digits | `PO0001`–`PO0150` | 150 |
| Supplier profile | Mongo `_id` | same as supplier ID | 100 |
| Raw ERP payload | `RAW` + 4 digits | `RAW0001`–`RAW0060` | 60 |

`purchase_orders` is owned by PostgreSQL. It is a minimal demo table outside the guide's core table list, matching `purchase_orders.json`: `id`, `supplier_id`, `product_id`, `quantity`, `unit_price`, `status`, and `created_at`.

### Supplier categories, locations, and statuses

Suppliers are split into four equal category blocks of 25:

| Supplier range | Category | Product range |
|---|---|---|
| `SUP0001`–`SUP0025` | `electronics` | `PRD0001`–`PRD0050` |
| `SUP0026`–`SUP0050` | `furniture` | `PRD0051`–`PRD0100` |
| `SUP0051`–`SUP0075` | `it_hardware` | `PRD0101`–`PRD0150` |
| `SUP0076`–`SUP0100` | `office_supplies` | `PRD0151`–`PRD0200` |

Allowed supplier statuses are `active`, `inactive`, and `suspended`.

- Default status is `active` for all suppliers except the explicit exceptions below.
- `inactive`: `SUP0018`, `SUP0037`, `SUP0083`.
- `suspended`: `SUP0061`, `SUP0091`.
- Resulting distribution: 95 active, 3 inactive, 2 suspended.

Locations are assigned round-robin in supplier-ID order:

```text
SUP0001 -> IN-TG
SUP0002 -> IN-AP
SUP0003 -> IN-KA
SUP0004 -> IN-MH
SUP0005 -> IN-TG
...repeat...
```

Allowed location codes are `IN-TG`, `IN-AP`, `IN-KA`, and `IN-MH`. All four must appear in the dataset.

### Products

Products are split into four category blocks of 50, matching the supplier block above. Every product has a category that is valid for its supplier's category block.

Product reference prices are deterministic and expressed in INR. The exact base prices are generator constants, with one explicit override:

- `PRD0114` (`it_hardware`) has a reference price of `52000.00`, used by the anomaly edge case below.
- All other products use deterministic category ranges and a fixed random seed.

### Quotations

Each supplier has exactly five quotations, assigned sequentially:

```text
supplier SUPnnnn -> QTN((n - 1) * 5 + 1) .. QTN(n * 5)
```

Examples:

- `SUP0001` owns `QTN00001`–`QTN00005`.
- `SUP0018` owns `QTN00086`–`QTN00090`.
- `SUP0100` owns `QTN00496`–`QTN00500`.

Within a supplier's five quotations, product selection cycles through that category's 50 products:

```text
category offset + ((supplier_index_in_category - 1 + quotation_slot) mod 50) + 1
```

where `quotation_slot` is `0`–`4`. This guarantees every quotation references an existing product in the same category as the supplier.

Quotation defaults:

- Currency: `INR`.
- `available_quantity`: at least the typical request quantity unless the quotation is an explicit insufficient-quantity edge case.
- `delivery_days`: 1–45 unless the quotation is an explicit long-delivery edge case.
- `valid_until`: `2026-04-01` (90 days after the reference date) unless the quotation is an explicit expired edge case.

**Typical request quantity for edge-case tests:** `100` units.

### Users

| User ID | Role |
|---|---|
| `USR0001` | `admin` |
| `USR0002`–`USR0004` | `requester` (3 users) |
| `USR0005`–`USR0014` | `approver` (10 users) |
| `USR0015` | `auditor` |

All user emails use the reserved `.test` domain, for example `user0001@example.test`. Password values in the seed file are placeholders; no plaintext demo password is stored.

## Deliberate edge cases

Edge cases are injected by exact ID after bulk generation. They must not be selected randomly.

### 1. Expired quotations

These five quotations have `valid_until` before `2026-01-01`.

| Quotation | Supplier | Product | `valid_until` |
|---|---|---|---|
| `QTN00011` | `SUP0003` | `PRD0003` | `2025-12-15` |
| `QTN00123` | `SUP0025` | `PRD0027` | `2025-11-30` |
| `QTN00245` | `SUP0049` | `PRD0078` | `2025-12-01` |
| `QTN00351` | `SUP0071` | `PRD0121` | `2025-10-31` |
| `QTN00489` | `SUP0098` | `PRD0176` | `2025-12-31` |

Expected behaviour: expired quotations are ineligible for recommendation when the request date is on or after the reference date.

### 2. Insufficient available quantity

These five quotations have `available_quantity` below the typical request quantity of `100`.

| Quotation | Supplier | Product | `available_quantity` |
|---|---|---|---:|
| `QTN00036` | `SUP0008` | `PRD0008` | 40 |
| `QTN00156` | `SUP0032` | `PRD0057` | 25 |
| `QTN00278` | `SUP0056` | `PRD0108` | 10 |
| `QTN00399` | `SUP0080` | `PRD0158` | 5 |
| `QTN00444` | `SUP0089` | `PRD0167` | 1 |

Expected behaviour: a quotation cannot satisfy a request whose quantity exceeds `available_quantity`.

### 3. Delivery above 45 days

| Quotation | Supplier | Product | `delivery_days` |
|---|---|---|---:|
| `QTN00066` | `SUP0014` | `PRD0014` | 46 |
| `QTN00178` | `SUP0036` | `PRD0063` | 50 |
| `QTN00299` | `SUP0060` | `PRD0113` | 60 |
| `QTN00356` | `SUP0072` | `PRD0122` | 75 |
| `QTN00471` | `SUP0095` | `PRD0170` | 90 |

Expected behaviour: these quotations are ineligible when a request constraint sets `max_delivery_days` to `45` or less.

### 4. Suppliers missing a required certification

The MVP required certification is `ISO9001` for all supplier categories. The following profiles deliberately omit it. All five suppliers are otherwise active and otherwise valid.

| Supplier | Category | Profile certifications |
|---|---|---|
| `SUP0007` | `electronics` | `["ISO14001"]` |
| `SUP0029` | `furniture` | `[]` |
| `SUP0053` | `it_hardware` | `["ISO14001", "ISO27001"]` |
| `SUP0074` | `it_hardware` | `["ISO14001"]` |
| `SUP0096` | `office_supplies` | `["ISO27001"]` |

Every other supplier profile must include `ISO9001`.

Expected behaviour: these suppliers are ineligible when ISO 9001 is required, even if their quotation is commercially attractive.

### 5. Inactive or suspended suppliers with attractive prices

These suppliers have a disqualifying status but a quotation priced 20% below the product's deterministic reference price, rounded to two decimal places.

| Supplier | Status | Quotation | Product |
|---|---|---|---|
| `SUP0018` | `inactive` | `QTN00087` | `PRD0019` |
| `SUP0061` | `suspended` | `QTN00303` | `PRD0113` |
| `SUP0083` | `inactive` | `QTN00413` | `PRD0160` |

Expected behaviour: the quotation may look attractive, but status disqualification must win. These records test that price is not the only ranking input.

### 6. Duplicate-looking supplier names

These are two distinct suppliers with different IDs, categories, locations, and registrations, but visually similar names.

| Supplier | Name | Category | Location |
|---|---|---|---|
| `SUP0012` | `Nova Components Pvt Ltd` | `electronics` | `IN-MH` |
| `SUP0013` | `Nova Components Pvt. Ltd.` | `electronics` | `IN-TG` |

Expected behaviour: the system must not merge or deduplicate them by name alone. Supplier ID is the identity key.

### 7. Unusually low price anomaly

| Quotation | Supplier | Product | Category | `unit_price` | Product reference price |
|---|---|---|---|---:|---:|
| `QTN00312` | `SUP0063` | `PRD0114` | `it_hardware` | `1200.00` | `52000.00` |

The price is approximately 97.7% below the product reference price. Expected behaviour: this quotation is flagged for anomaly discussion, not silently accepted or automatically rejected. The deterministic comparison and LLM explanation must both call out the abnormal price.

## MongoDB supplier profiles

One document per supplier is written to `supplier_profiles`. `_id` equals the PostgreSQL supplier ID.

Required shape:

```json
{
  "_id": "SUP0001",
  "supplier_type": "electronics",
  "certifications": ["ISO9001", "ISO14001"],
  "regional_registrations": {
    "IN-TG": "REG-0001"
  },
  "compliance": {
    "risk_level": "low",
    "verification_status": "verified"
  },
  "source": {
    "system": "demo_erp",
    "last_synced_at": "2026-01-01T10:00:00Z"
  }
}
```

Rules:

- `supplier_type` must equal the supplier's PostgreSQL category.
- `certifications` is an array of certification codes. `ISO9001` is required except for the five explicit missing-certification suppliers above.
- `regional_registrations` maps location codes to registration IDs.
- `compliance.risk_level` is one of `low`, `medium`, `high`.
- `compliance.verification_status` is one of `verified`, `pending`, `failed`.
- `source.system` is `demo_erp`; `source.last_synced_at` is a fixed ISO timestamp.
- Core identity fields (`name`, `status`, `category`) are owned by PostgreSQL and must not be duplicated as authoritative fields in Mongo.

## Raw external ERP payloads

`raw_supplier_payloads.jsonl` contains exactly 60 records: 55 valid and 5 deliberately malformed or partial. Each line is a valid JSON object.

Valid record shape:

```json
{
  "payload_id": "RAW0001",
  "source_system": "demo_erp",
  "fetched_at": "2026-01-01T10:00:00Z",
  "payload": {
    "supplier_id": "SUP0001",
    "supplier_name": "Acme Electronics Pvt Ltd",
    "category": "electronics",
    "location": "IN-TG",
    "contact": {
      "email": "vendor0001@example.test",
      "phone": "+91-0000000001"
    },
    "certifications": ["ISO9001", "ISO14001"],
    "regional_registrations": {
      "IN-TG": "REG-0001"
    }
  },
  "processing_status": "raw"
}
```

Allowed `processing_status` values are `raw`, `parsed`, and `failed`.

The five malformed or partial records are:

| Record | Problem | Expected handling |
|---|---|---|
| `RAW0007` | `payload` is missing `supplier_id` | Mark `processing_status: "failed"` and add a short `error` |
| `RAW0019` | `category` is `null` and `contact` is missing | Mark `failed` with a validation error |
| `RAW0031` | `certifications` is a string instead of an array | Mark `failed` with a type error |
| `RAW0043` | `payload` is truncated and contains only `supplier_name` and `location` | Mark `failed` as incomplete |
| `RAW0055` | `supplier_id` is `SUP9999`, which does not exist | Mark `failed` as an unknown supplier |

The malformed records must still be parseable JSON so the seeder can persist them as failed raw payloads rather than crashing the whole import.

## Determinism and file formatting

- Use a fixed random seed of `42`.
- Use stable ID helpers: `supplier_id(n)`, `product_id(n)`, `quotation_id(n)`, `user_id(n)`.
- Inject all documented edge cases explicitly by ID after bulk generation.
- JSON files: UTF-8, `indent=2`, `sort_keys=True`, trailing newline.
- JSONL files: one compact JSON object per line with sorted keys, trailing newline.
- Never use `datetime.now()` or other ambient state.
- Regenerating without code changes must produce byte-identical output.
- `--check` must regenerate in memory and compare byte-for-byte with the files on disk.

## Consequences

- Tests can target stable IDs without searching for edge cases at runtime.
- The dataset covers expiry, quantity, delivery, certification, status, identity, and price-anomaly failures.
- The generator must treat this document as its contract. Changing an edge-case ID or value requires updating this ADR and the generator together.
- The dataset remains safe to commit because it contains only synthetic `.test` identities and no secrets.
