---
document_id: POL-002
title: Approval Matrix
version: "4.1"
effective_from: 2026-01-01
effective_to: null
classification: internal
owner: procurement
supersedes: null
status: active
---

# Approval Matrix

## 1. How to use this matrix

### 1.1 Estimated value

Calculate estimated value as quotation unit price multiplied by requested quantity. Use the quotation currency; the MVP dataset uses INR only.

### 1.2 Multiple approvers

Where more than one approver is listed, all listed approvals are required. Approvals may be collected in parallel.

### 1.3 Self-approval prohibition

A requester cannot approve their own request. An approver who has a conflict of interest must decline and escalate.

## 2. Standard value bands

### 2.1 Value band table

- Band A, up to INR 50,000: line manager.
- Band B, above INR 50,000 up to INR 5,00,000: procurement approver.
- Band C, above INR 5,00,000 up to INR 25,00,000: procurement manager plus finance approver.
- Band D, above INR 25,00,000: finance director plus procurement administrator.

### 2.2 Boundary rule

A value exactly on a boundary belongs to the lower band. For example, INR 5,00,000 is Band B, while INR 5,00,001 is Band C.

### 2.3 Currency

All amounts in this matrix are in Indian rupees. A non-INR quotation requires a finance conversion record before approval.

## 3. Category-specific rules

### 3.1 Laptop and IT hardware approvals

A laptop purchase uses the `it_hardware` category. In addition to the value band, the following quantity rules apply:

- 1 to 25 laptops: procurement approver.
- 26 to 100 laptops: IT manager and procurement manager.
- More than 100 laptops: finance director.
- More than 250 laptops: finance director and procurement administrator.

A request for 500 laptops therefore requires finance director and procurement administrator approval.

### 3.2 Electronics thresholds

Electronics purchases above INR 10,00,000 require a category approver in addition to the value-band approver.

### 3.3 Furniture thresholds

Furniture purchases above INR 8,00,000 require a facilities approver in addition to the value-band approver.

### 3.4 Office supplies thresholds

Office supplies above INR 2,00,000 require a procurement approver. Routine office supplies below INR 10,000 may use the pre-approved catalogue process.

## 4. Delivery and certification gates

### 4.1 Delivery gate

A quotation with a delivery estimate above 45 calendar days requires an exception approval. The exception must name the number of days and the business reason.

### 4.2 Certification gate

A supplier missing `ISO9001` cannot be approved for any category covered by this policy. An exception cannot waive this certification in the MVP.

### 4.3 Quantity gate

A quotation whose available quantity is below the requested quantity cannot be approved for that request.

## 5. Decision recording

### 5.1 Required fields

An approval decision records the request identifier, approver identifier, decision, reason, recommendation version, and decision time.

### 5.2 Rejection

A rejection must state at least one actionable reason, such as price, delivery, certification, or policy conflict.

### 5.3 Re-submission

After a material change to the request or recommendation, the requester must obtain a new recommendation version and fresh approvals.

## 6. Escalation

### 6.1 Missing approver

If the designated approver is unavailable for more than one business day, escalation goes to the next role in the same function.

### 6.2 Policy conflict

If the matrix conflicts with an active policy, the stricter approval requirement applies until the policy owner resolves the conflict.
