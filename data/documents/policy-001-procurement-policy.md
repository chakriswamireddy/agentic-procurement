---
document_id: POL-001
title: Procurement Policy
version: "3.2"
effective_from: 2026-01-01
effective_to: null
classification: internal
owner: procurement
supersedes: POL-011
status: active
---

# Procurement Policy

## 1. Purpose and scope

### 1.1 Purpose

This policy defines how the organisation requests, evaluates, approves, and records purchases. It applies to all employees, contractors, and approved suppliers acting on the organisation's behalf.

### 1.2 Scope

The policy covers goods and services purchased with organisational funds, including electronics, furniture, IT hardware, and office supplies. It does not cover payroll, taxes, or statutory payments.

### 1.3 Policy precedence

An active policy version takes precedence over an obsolete or draft version. Where two active documents conflict, the approval matrix in POL-002 controls approval routing and this policy controls eligibility and evidence requirements.

## 2. Roles and responsibilities

### 2.1 Requester

The requester defines the business need, product, quantity, delivery deadline, and any mandatory constraints. The requester must not approve their own request.

### 2.2 Approver

An approver reviews the recommendation, the supporting evidence, and the policy citations. Approval must be recorded against a specific recommendation version.

### 2.3 Procurement administrator

The administrator maintains supplier records, policy documents, and configuration. The administrator may correct data but must not bypass an approval threshold.

## 3. Supplier eligibility

### 3.1 General conditions

A supplier is eligible only when it is `active`, the quotation is valid on the request date, the available quantity is at least the requested quantity, and the quoted delivery is within the request limit.

### 3.2 Required certification

Suppliers must hold a current `ISO9001` certification for the categories covered by this policy. A supplier missing `ISO9001` is ineligible even when its price is the lowest.

### 3.3 Status disqualification

Suppliers with `inactive` or `suspended` status are ineligible. Price competitiveness never overrides a disqualifying status.

### 3.4 Quotation validity

A quotation with `valid_until` earlier than the request date is expired and must not be used. The decision record must cite the quotation identifier and its validity date.

## 4. Approval thresholds and laptop purchases

### 4.1 Standard approval thresholds

The estimated value of a purchase is the quotation unit price multiplied by the requested quantity.

- Up to INR 50,000: the requester's line manager must approve.
- Above INR 50,000 and up to INR 5,00,000: a procurement approver must approve.
- Above INR 5,00,000 and up to INR 25,00,000: the procurement manager and a finance approver must approve.
- Above INR 25,00,000: the finance director and the procurement administrator must approve.

### 4.2 Approval evidence

Every approval must record the recommendation version, the selected supplier and quotation, the policy clauses used, and any exceptions. A recommendation without evidence is not assignable for approval.

### 4.3 Laptop purchases

Laptops are classified under `it_hardware`. A laptop purchase requires an `it_hardware` supplier, a valid quotation, and `ISO9001` certification.

- A request for 1 to 25 laptops requires a procurement approver.
- A request for 26 to 100 laptops requires the IT manager and a procurement manager.
- A request above 100 laptops requires the finance director.
- The standard delivery limit for laptops is 45 calendar days.
- The standard warranty for laptops is at least 36 months.

For illustration, a request for 500 laptops at an indicative unit price of INR 60,000 has an estimated value of INR 3,00,00,000 and therefore requires finance director approval.

Tablets, desktop workstations, monitors, docking stations, and laptop bags are not laptops and follow their own category rules.

### 4.4 Laptop request constraints

A laptop request should state the required quantity, maximum delivery days, minimum warranty months, and any required certification. The default quantity baseline for comparison is 100 units unless the request states otherwise.

## 5. Evaluation and anomaly handling

### 5.1 Deterministic comparison

Supplier comparison must use the same inputs and rules for every run. The comparison score weights price at 60 percent, delivery at 20 percent, and compliance at 20 percent.

### 5.2 Ineligible options

Expired quotations, insufficient available quantity, delivery above the request limit, missing `ISO9001`, and inactive or suspended suppliers must be excluded before scoring.

### 5.3 Price anomaly review

A quotation priced more than 40 percent below the median eligible price must be flagged for anomaly review. The recommendation may discuss the anomaly but must not silently accept it.

## 6. Records and audit

### 6.1 Required records

The organisation retains the request, recommendation version, approval decision, execution record, and audit events. Each record must reference the supplier and quotation identifiers used.

### 6.2 Record integrity

Business records must not be deleted when a supplier or product record changes. Supplier and product references therefore use restricted deletion.

## 7. Exceptions

### 7.1 Exception approval

An exception to a delivery, warranty, or certification requirement must be approved one level above the normal threshold. The exception reason and expiry must be recorded.

### 7.2 No retroactive approval

A purchase must not be executed before the required approval is recorded. Retroactive approval is limited to the emergency procedure in POL-009.
