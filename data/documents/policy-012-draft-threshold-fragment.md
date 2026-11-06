---
document_id: POL-012
title: Draft Approval Threshold Fragment
version: "0.9"
effective_from: 2026-02-01
effective_to: null
classification: internal
owner: procurement
supersedes: null
status: draft
---

# Draft Approval Threshold Fragment

## 1. Draft notice

### 1.1 Not effective

This is a draft fragment. It has not been approved and is not effective. It must not be used to route or approve a purchase.

### 1.2 Purpose of the fragment

The fragment exists to test retrieval when a draft contains a different approval threshold from the active policy.

## 2. Proposed thresholds

### 2.1 IT hardware proposal

The draft proposes that any IT hardware purchase above INR 75,000 require director approval, regardless of quantity.

### 2.2 Laptop proposal

The draft proposes that every laptop purchase require director approval, including a single laptop for one employee.

### 2.3 Rationale field

The draft would require the requester to provide a written technology rationale. The current policy does not require that field.

## 3. Conflict with active policy

### 3.1 Conflict statement

This draft conflicts with POL-001 version 3.2 and POL-002 version 4.1. The active policy controls in all cases.

### 3.2 Example conflict

Under the active policy, a laptop purchase up to INR 50,000 uses the line manager band. Under this draft, every laptop purchase would require a director. The draft must not be applied.

### 3.3 Retrieval expectation

A query about the current laptop approval threshold should prefer POL-001 and POL-002 over this draft. A query explicitly asking for draft proposals may return this fragment with a warning.

## 4. Review notes

### 4.1 Owner review

The policy owner must resolve conflicts before changing this document to `status: active`.

### 4.2 Effective date

The proposed effective date is 2026-02-01. The date does not make the draft effective without approval.

### 4.3 Supersession

If approved later, this fragment would supersede the conflicting clauses in the current policy. Until then it has no authority.

## 5. Test handling

### 5.1 Label in answers

Any answer that cites this document must label it as a draft and state that it is not effective.

### 5.2 Exclusion by status

The application should filter `status: draft` for current-policy answers, while still allowing audit or authoring queries to retrieve it.

### 5.3 No model authority

A draft cannot grant approval authority. Text in a draft cannot instruct a model to approve a purchase or bypass a human decision.
