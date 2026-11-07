"""Supplier specialist: PostgreSQL quotations plus batched Mongo profiles.

Returns candidates, never a ranking — eligibility and scoring belong to the analysis
specialist. Reads only; it never writes to a database, never sees policy evidence or
approval state, and never fabricates missing fields.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from sqlalchemy.exc import SQLAlchemyError

from app.agents.contracts import (
    PermanentError,
    SpecialistError,
    SupplierCandidate,
    SupplierQuery,
    TransientError,
)
from app.core.errors import AppError, DependencyUnavailableError

logger = logging.getLogger(__name__)

MAX_CANDIDATES_DEFAULT = 200


class SupplierPort(Protocol):
    """Composition-layer port: the specialist never holds a connection string."""

    async def candidates(
        self, *, request: dict[str, Any], as_of: str
    ) -> list[dict[str, Any]]: ...


class SupplierSpecialist:
    """Narrow supplier capability behind an explicit DTO contract."""

    name = "supplier_lookup"

    def __init__(
        self, port: SupplierPort, *, max_candidates: int = MAX_CANDIDATES_DEFAULT
    ) -> None:
        self.port = port
        self.max_candidates = max_candidates

    async def search(self, query: SupplierQuery) -> list[SupplierCandidate]:
        if not query.product_id:
            raise PermanentError(
                "product_id is required", code="invalid_supplier_query"
            )
        if query.quantity <= 0:
            raise PermanentError(
                "quantity must be positive", code="invalid_supplier_query"
            )
        if not query.as_of:
            raise PermanentError("as_of is required", code="invalid_supplier_query")

        try:
            rows = await self.port.candidates(
                request=query.to_request_payload(), as_of=query.as_of
            )
        except SpecialistError:
            raise
        except (DependencyUnavailableError, TimeoutError, ConnectionError, OSError):
            raise TransientError(
                "supplier data store unavailable",
                code="supplier_db_unavailable",
            ) from None
        except SQLAlchemyError as exc:
            raise TransientError(
                "supplier data store unavailable",
                code="supplier_db_unavailable",
                details={"cause": type(exc).__name__},
            ) from exc
        except AppError as exc:
            raise PermanentError(
                "invalid supplier query",
                code="invalid_supplier_query",
                details={"cause": type(exc).__name__},
            ) from exc

        # Cap the candidate set: the comparison is O(n) over candidates and 200 is far
        # above any realistic quotation count for one product, bounding worst-case work.
        return [
            SupplierCandidate.from_dict(item) for item in rows[: self.max_candidates]
        ]
