"""Model Context Protocol (MCP) server for procurement actions.

Five typed tools. ``create_purchase_request`` independently verifies the
approval row before writing an execution record — never trusts the caller.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import select

from app.database.postgres.models import (
    ExecutionRecord,
    ProcurementRequest,
    Quotation,
    Supplier,
)
from app.database.postgres.session import get_session_factory
from app.mcp.authz import find_existing_execution, verify_approval_for_execution
from app.mcp.schemas import (
    CreatePurchaseRequestInput,
    CreatePurchaseRequestOutput,
    GetPolicyEvidenceInput,
    GetPolicyEvidenceOutput,
    GetPurchaseRequestStatusInput,
    GetPurchaseRequestStatusOutput,
    GetSupplierQuotationInput,
    GetSupplierQuotationOutput,
    QuotationOut,
    SearchSuppliersInput,
    SearchSuppliersOutput,
    SupplierCandidateOut,
    error_payload,
)

logger = logging.getLogger(__name__)

mcp_server = MCPServer("procurement-service")


async def _session():
    return get_session_factory()()


@mcp_server.tool()
async def search_suppliers(
    category: str,
    quantity: int,
    max_delivery_days: int | None = None,
) -> dict[str, Any]:
    """Search active suppliers by category, optionally filtering delivery days."""
    try:
        parsed = SearchSuppliersInput(
            category=category, quantity=quantity, max_delivery_days=max_delivery_days
        )
    except Exception as exc:
        raise ToolError(
            error_payload("invalid_arguments", str(exc)).get("message", "invalid arguments")
        ) from exc

    async with await _session() as session:
        statement = select(Supplier).where(
            Supplier.status == "active", Supplier.category == parsed.category
        )
        suppliers = (await session.execute(statement)).scalars().all()

    candidates = [
        SupplierCandidateOut(
            supplier_id=s.id,
            name=s.name,
            category=s.category,
            location=s.location,
            status=s.status,
        )
        for s in suppliers[:50]
    ]
    output = SearchSuppliersOutput(candidates=candidates, count=len(candidates))
    return output.model_dump()


@mcp_server.tool()
async def get_supplier_quotation(supplier_id: str, product_id: str) -> dict[str, Any]:
    """Return the latest quotation for a supplier/product pair."""
    try:
        parsed = GetSupplierQuotationInput(
            supplier_id=supplier_id, product_id=product_id
        )
    except Exception as exc:
        raise ToolError(str(exc)) from exc

    async with await _session() as session:
        row = (
            await session.execute(
                select(Quotation)
                .where(
                    Quotation.supplier_id == parsed.supplier_id,
                    Quotation.product_id == parsed.product_id,
                )
                .order_by(Quotation.valid_until.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    if row is None:
        raise ToolError("quotation_not_found: no quotation for supplier/product")

    output = GetSupplierQuotationOutput(
        quotation=QuotationOut(
            quotation_id=row.id,
            supplier_id=row.supplier_id,
            product_id=row.product_id,
            unit_price=str(row.unit_price),
            currency=row.currency,
            available_quantity=int(row.available_quantity),
            delivery_days=int(row.delivery_days),
            valid_until=row.valid_until.isoformat() if row.valid_until else None,
        )
    )
    return output.model_dump()


@mcp_server.tool()
async def get_policy_evidence(
    query: str,
    as_of: str | None = None,
    classification: str | None = None,
) -> dict[str, Any]:
    """Retrieve policy evidence snippets for a query (read-only helper).

    In this MVP the tool returns an empty, inconclusive result when the RAG
    runtime is not wired into the MCP process; the API path remains authoritative.
    """
    try:
        GetPolicyEvidenceInput(query=query, as_of=as_of, classification=classification)
    except Exception as exc:
        raise ToolError(str(exc)) from exc

    output = GetPolicyEvidenceOutput(evidence=[], inconclusive=True)
    return output.model_dump()


@mcp_server.tool()
async def create_purchase_request(
    request_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Create a simulated purchase request after independent approval verification.

    Accepts only request identity and an idempotency key — never price, supplier,
    or quantity. Rejected without a valid approval row for the current version.
    """
    try:
        parsed = CreatePurchaseRequestInput(
            request_id=request_id, idempotency_key=idempotency_key
        )
    except Exception as exc:
        raise ToolError(f"invalid_arguments: {exc}") from exc

    async with await _session() as session:
        check = await verify_approval_for_execution(
            session, request_id=parsed.request_id
        )
        if not check.allowed:
            logger.warning(
                "mcp create_purchase_request denied",
                extra={
                    "request_id": parsed.request_id,
                    "code": check.code,
                    "idempotency_key": parsed.idempotency_key,
                },
            )
            raise ToolError(f"{check.code}: {check.message}")

        existing = await find_existing_execution(
            session,
            request_id=parsed.request_id,
            idempotency_key=parsed.idempotency_key,
        )
        if existing is not None:
            if existing.idempotency_key != parsed.idempotency_key:
                raise ToolError(
                    "idempotency_conflict: different idempotency key for existing execution"
                )
            output = CreatePurchaseRequestOutput(
                external_reference=existing.external_reference or "",
                status="exists",
                request_id=parsed.request_id,
                idempotency_key=parsed.idempotency_key,
            )
            return output.model_dump()

        version = check.recommendation_version or 1
        external_reference = f"SIM-{parsed.request_id}-{version}"
        record = ExecutionRecord(
            id=f"EXE-{uuid.uuid4().hex}",
            request_id=parsed.request_id,
            idempotency_key=parsed.idempotency_key,
            external_reference=external_reference,
            status="succeeded",
            error_code=None,
            created_at=datetime.now(UTC),
        )
        session.add(record)
        request = await session.get(ProcurementRequest, parsed.request_id)
        if request is not None and request.status in (
            "approved",
            "awaiting_approval",
            "resuming",
        ):
            request.status = "executing"
        await session.commit()

    logger.info(
        "mcp create_purchase_request ok",
        extra={
            "request_id": parsed.request_id,
            "idempotency_key": parsed.idempotency_key,
            "external_reference": external_reference,
        },
    )
    output = CreatePurchaseRequestOutput(
        external_reference=external_reference,
        status="created",
        request_id=parsed.request_id,
        idempotency_key=parsed.idempotency_key,
    )
    return output.model_dump()


@mcp_server.tool()
async def get_purchase_request_status(external_reference: str) -> dict[str, Any]:
    """Look up execution status by external reference (reconciliation helper)."""
    try:
        parsed = GetPurchaseRequestStatusInput(external_reference=external_reference)
    except Exception as exc:
        raise ToolError(str(exc)) from exc

    async with await _session() as session:
        row = (
            await session.execute(
                select(ExecutionRecord).where(
                    ExecutionRecord.external_reference == parsed.external_reference
                )
            )
        ).scalar_one_or_none()
    if row is None:
        raise ToolError("execution_not_found: no execution for external_reference")

    output = GetPurchaseRequestStatusOutput(
        external_reference=row.external_reference or parsed.external_reference,
        status=row.status,
        updated_at=row.created_at.isoformat() if row.created_at else None,
    )
    return output.model_dump()


def main() -> None:
    """Entry point for ``python -m app.mcp.server`` (stdio transport)."""
    mcp_server.run(transport="stdio")


if __name__ == "__main__":
    main()
