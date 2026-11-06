---
document_id: POL-003
title: Supplier Onboarding Guidelines
version: "2.3"
effective_from: 2026-01-01
effective_to: null
classification: internal
owner: procurement
supersedes: null
status: active
---

# Supplier Onboarding Guidelines

## 1. Purpose

### 1.1 Goal

Onboarding establishes a reliable, auditable supplier record before any quotation is used in a recommendation. It separates core supplier identity from supplementary profile data.

### 1.2 Ownership

PostgreSQL owns supplier identity, category, location, and status. MongoDB stores flexible profile extensions and raw integration payloads.

## 2. Required supplier information

### 2.1 Core identity

Every supplier record must contain a stable supplier ID, legal name, category, location code, and status. The supplier ID is the identity key; similar names do not justify merging records.

### 2.2 Contact information

The profile must include a business email and phone number for the procurement contact. Personal contact details must not be used as the supplier identity.

### 2.3 Certifications

The profile must list current certifications. `ISO9001` is mandatory for all categories in the MVP. `ISO14001` and `ISO27001` are recorded when available.

### 2.4 Regional registration

Each supplier must provide a registration identifier for its operating location, for example `IN-TG` or `IN-KA`.

## 3. Verification steps

### 3.1 Document check

The onboarding team verifies the certification name, issuer, expiry date, and registration identifier. Expired certifications are recorded as missing.

### 3.2 Compliance check

The profile records `compliance.risk_level` as `low`, `medium`, or `high`, and `compliance.verification_status` as `verified`, `pending`, or `failed`.

### 3.3 Sample review

For a new category, the team reviews at least one sample quotation and confirms the unit of measure, currency, availability, delivery estimate, and validity date.

### 3.4 Duplicate-name review

Two suppliers with similar names remain separate records unless a documented legal-entity check proves they are the same organisation. `SUP0012` and `SUP0013` are deliberately similar names used for this test.

## 4. Approval to activate

### 4.1 Activation criteria

A supplier may be activated only when core identity is complete, `ISO9001` is current, the compliance check is verified, and procurement approves the record.

### 4.2 Pending suppliers

A supplier with `verification_status: pending` may be onboarded but cannot receive a recommendation until verification is complete.

### 4.3 Failed verification

A supplier with `verification_status: failed` must remain inactive. Re-onboarding requires a new verification record.

## 5. Status changes

### 5.1 Suspension

Procurement may suspend a supplier for a compliance breach, repeated late delivery, or a failed security review. Existing purchase orders remain valid unless the contract says otherwise.

### 5.2 Inactivation

A supplier may be inactivated when it stops trading or no longer serves the category. Historical quotations and orders remain in the system for audit.

### 5.3 Reactivation

Reactivation requires a fresh certification check and procurement approval. The previous status change reason must be retained.

## 6. Integration rules

### 6.1 Raw payload retention

External ERP payloads are stored as received, including malformed or partial records. Failed payloads must include a short error field and must not overwrite a valid profile.

### 6.2 Source metadata

Each profile records `source.system` and `source.last_synced_at`. The MVP source system is `demo_erp`.

### 6.3 No duplicated ownership

The Mongo profile must not contain authoritative supplier name, status, or category fields. Those fields are read from PostgreSQL.
