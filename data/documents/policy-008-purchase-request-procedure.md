---
document_id: POL-008
title: Purchase Request Procedure
version: "1.9"
effective_from: 2026-01-01
effective_to: null
classification: internal
owner: procurement
supersedes: null
status: active
---

# Purchase Request Procedure

## 1. Creating a request

### 1.1 Required fields

A purchase request must include a requester, product, category, quantity, required-by date, and any constraints. The requester must state the business need in plain language.

### 1.2 Quantity

Quantity must be a positive whole number. The request must not combine unrelated products into one line to avoid an approval threshold.

### 1.3 Constraints

Supported constraints include `max_delivery_days`, `required_certifications`, `min_warranty_months`, and a maximum budget. Constraints are stored as structured JSON, not free text.

### 1.4 Example constraints

A standard laptop request might use `{"max_delivery_days": 45, "required_certifications": ["ISO9001"], "min_warranty_months": 36}`.

## 2. Validation

### 2.1 Request validity

The application rejects a request with a missing product, non-positive quantity, unknown requester, or invalid constraint. Rejection reasons are shown to the requester.

### 2.2 Category consistency

The product category must match the supplier category used for quotation selection. A laptop request therefore selects an `it_hardware` supplier.

### 2.3 Duplicate request

A requester should check for an open request for the same product and quantity. Duplicate requests may be merged before evaluation.

## 3. Supplier search

### 3.1 Eligible suppliers

The search returns active suppliers with a valid quotation, sufficient available quantity, `ISO9001`, and delivery within the request limit.

### 3.2 Ineligible evidence

The system records why a supplier was excluded. A price leader with `suspended` status is excluded with the status reason, not ranked.

### 3.3 Quotation selection

When a supplier has more than one quotation for a product, the system uses the valid quotation with the latest `valid_until`, then the lower price. The rule must be deterministic.

## 4. Recommendation

### 4.1 Scoring

The recommendation applies the weights in POL-001 and records each component score. The recommendation version starts at 1 and increments after any material change.

### 4.2 Evidence

The recommendation includes supplier and quotation identifiers plus policy citations. A policy citation must include the document ID, version, and clause.

### 4.3 Anomaly flag

A price more than 40 percent below the median eligible price is flagged for review. The recommendation states the flag but does not automatically reject the quotation.

## 5. Approval

### 5.1 Laptop purchase example

A request for 500 laptops has a baseline quantity of 500, not the default 100. It requires `it_hardware` suppliers, a 45-day maximum delivery, a 36-month minimum warranty, and finance director approval because the estimated value exceeds INR 25,00,000.

### 5.2 Approval route

The application determines the approval route from the estimated value and the category rules. The requester cannot approve the request.

### 5.3 Decision

The approver records `approved` or `rejected` with a reason and the recommendation version. A changed recommendation requires a new decision.

## 6. Execution and close-out

### 6.1 Pre-execution check

Before creating a purchase order, the application verifies that the request is approved, the recommendation version matches, and the idempotency key has not been used.

### 6.2 Execution record

The execution record contains the request ID, idempotency key, external reference, status, and error code if applicable.

### 6.3 Close-out

The request is closed after delivery acceptance and any warranty record is created. Audit events remain available after close-out.
