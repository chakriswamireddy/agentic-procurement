"""Coordinates business records, graph execution, and API views."""

import logging
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from langgraph.types import Command
from pymongo.asynchronous.database import AsyncDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError, ValidationError, WorkflowError
from app.database.postgres.models import User
from app.graph.dependencies import build_dependencies, use_dependencies
from app.repositories.audit_repository import AuditRepository
from app.repositories.recommendation_repository import RecommendationRepository
from app.repositories.request_repository import RequestRepository
from app.schemas.procurement import RecommendationSummary
from app.schemas.workflow import WorkflowView
from app.services.result_service import ResultService

logger = logging.getLogger(__name__)


class WorkflowService:
    def __init__(
        self,
        settings: Settings,
        graph: Any,
        *,
        session: AsyncSession,
        mongo_db: AsyncDatabase,
        policy_service: Any,
    ) -> None:
        self.settings = settings
        self.graph = graph
        self.session = session
        self.mongo_db = mongo_db
        self.policy_service = policy_service

    def _config(self, thread_id: str) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": self.settings.workflow_recursion_limit,
        }

    def _as_of(self) -> str:
        value = self.settings.workflow_as_of or date.today()
        return value.isoformat()

    @staticmethod
    def _jsonable(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (date,)):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): WorkflowService._jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [WorkflowService._jsonable(item) for item in value]
        return value

    @classmethod
    def _constraints(cls, value: dict[str, Any] | None) -> dict[str, Any]:
        if not value:
            return {}
        if not isinstance(value, dict):
            raise ValidationError("constraints must be an object")
        return cls._jsonable(value)

    async def _audit(
        self,
        *,
        event_type: str,
        request_id: str,
        actor_id: str | None,
        correlation_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        await AuditRepository(self.session).append(
            event_type=event_type,
            request_id=request_id,
            actor_id=actor_id,
            correlation_id=correlation_id,
            details=details,
        )

    async def create_and_start(
        self,
        *,
        requester_id: str,
        product_id: str,
        quantity: int,
        constraints: dict[str, Any] | None,
        correlation_id: str,
        request_id: str | None = None,
    ) -> WorkflowView:
        requests = RequestRepository(self.session)
        product = await requests.get_product(product_id)
        if product is None:
            raise ValidationError(f"product {product_id} not found")
        if quantity <= 0:
            raise ValidationError("quantity must be positive")
        if await self.session.get(User, requester_id) is None:
            raise ValidationError(f"requester {requester_id} not found")

        normalized_constraints = self._constraints(constraints)
        if request_id and await requests.get_request(request_id) is not None:
            return await self.start(
                request_id=request_id,
                user_id=requester_id,
                correlation_id=correlation_id,
            )

        identifier = request_id or f"PRQ-{uuid.uuid4().hex[:12].upper()}"
        await requests.create(
            request_id=identifier,
            requester_id=requester_id,
            product_id=product_id,
            quantity=quantity,
            constraints=normalized_constraints,
            status="received",
        )
        await self._audit(
            event_type="request_created",
            request_id=identifier,
            actor_id=requester_id,
            correlation_id=correlation_id,
            details={"product_id": product_id, "quantity": quantity},
        )
        await self._audit(
            event_type="workflow_started",
            request_id=identifier,
            actor_id=requester_id,
            correlation_id=correlation_id,
        )
        await self.session.commit()

        return await self.start(
            request_id=identifier,
            user_id=requester_id,
            correlation_id=correlation_id,
        )

    def _initial_state(
        self, *, request: dict[str, Any], user_id: str, correlation_id: str
    ) -> dict[str, Any]:
        return {
            "request_id": request["id"],
            "thread_id": request["id"],
            "user_id": user_id,
            "correlation_id": correlation_id,
            "as_of": self._as_of(),
            "request": {
                "product_id": request["product_id"],
                "product_name": request["product_name"],
                "category": request["category"],
                "quantity": int(request["quantity"]),
                "currency": "INR",
                "constraints": request.get("constraints") or {},
            },
            "errors": [],
            "status": "received",
        }

    def _dependencies(self):
        return build_dependencies(
            self.settings,
            session=self.session,
            mongo_db=self.mongo_db,
            policy_service=self.policy_service,
        )

    async def start(
        self, *, request_id: str, user_id: str, correlation_id: str
    ) -> WorkflowView:
        requests = RequestRepository(self.session)
        request = await requests.get_request_view(request_id)
        if request is None:
            raise NotFoundError(f"procurement request {request_id} not found")

        config = self._config(request_id)
        snapshot = await self.graph.aget_state(config)
        if snapshot.values:
            return await self.get_status(request_id)

        state = self._initial_state(
            request=request, user_id=user_id, correlation_id=correlation_id
        )
        try:
            with use_dependencies(self._dependencies()):
                result = await self.graph.ainvoke(state, config)
        except Exception as exc:
            logger.exception(
                "workflow start failed",
                extra={"path": f"/workflows/{request_id}"},
            )
            await self._mark_failed(state, exc)
            raise WorkflowError("workflow execution failed") from exc

        await self._sync_status(result)
        return await self.get_status(request_id)

    async def get_request(self, request_id: str) -> Any:
        request = await RequestRepository(self.session).get_request_view(request_id)
        if request is None:
            raise NotFoundError(f"procurement request {request_id} not found")

        record = await RecommendationRepository(self.session).get_latest(request_id)
        recommendation = None
        if record is not None:
            recommendation = self._summary(self._recommendation_from_record(record))

        return {
            "id": request["id"],
            "thread_id": request["id"],
            "requester_id": request["requester_id"],
            "product_id": request["product_id"],
            "product_name": request["product_name"],
            "category": request["category"],
            "quantity": request["quantity"],
            "constraints": request.get("constraints") or {},
            "status": request["status"],
            "created_at": request["created_at"],
            "recommendation": recommendation,
        }

    async def get_status(self, thread_id: str) -> WorkflowView:
        config = self._config(thread_id)
        snapshot = await self.graph.aget_state(config)
        values = dict(snapshot.values or {})

        request = await RequestRepository(self.session).get_request_view(thread_id)
        if not values and request is None:
            raise NotFoundError(f"workflow {thread_id} not found")

        status = values.get("status") or (request or {}).get("status") or "received"
        current_node = None
        if snapshot.next:
            current_node = snapshot.next[0]

        recommendation = values.get("recommendation")
        if recommendation is None:
            record = await RecommendationRepository(self.session).get_latest(thread_id)
            if record is not None:
                recommendation = self._recommendation_from_record(record)

        evidence = values.get("policy_evidence") or []
        evidence_ids = [
            str(item["chunk_id"])
            for item in evidence
            if isinstance(item, dict) and item.get("chunk_id")
        ]
        if not evidence_ids and recommendation:
            evidence_ids = [
                str(item["chunk_id"])
                for item in recommendation.get("evidence") or []
                if isinstance(item, dict) and item.get("chunk_id")
            ]

        validation = values.get("validation") or {}
        return WorkflowView(
            request_id=values.get("request_id") or thread_id,
            thread_id=thread_id,
            status=status,
            current_node=current_node,
            awaiting_approval=status == "awaiting_approval",
            failure_reason=values.get("failure_reason"),
            recommendation=self._summary(recommendation),
            evidence_chunk_ids=evidence_ids,
            issues=validation.get("issues") or [],
        )

    async def resume(self, thread_id: str, decision: dict[str, Any]) -> WorkflowView:
        config = self._config(thread_id)
        snapshot = await self.graph.aget_state(config)
        values = dict(snapshot.values or {})
        if not values:
            raise NotFoundError(f"workflow {thread_id} not found")
        if values.get("status") != "awaiting_approval":
            raise ConflictError("workflow is not awaiting approval")

        try:
            with use_dependencies(self._dependencies()):
                result = await self.graph.ainvoke(Command(resume=decision), config)
        except Exception as exc:
            logger.exception(
                "workflow resume failed",
                extra={"path": f"/workflows/{thread_id}"},
            )
            await self._mark_failed(values, exc)
            raise WorkflowError("workflow resume failed") from exc

        await self._sync_status(result)
        return await self.get_status(thread_id)

    async def _sync_status(self, state: dict[str, Any]) -> None:
        status = state.get("status")
        if not status:
            return
        await ResultService(
            RequestRepository(self.session), AuditRepository(self.session)
        ).mark_status(
            state=state,
            status=status,
            event_type="workflow_status_changed",
        )

    async def _mark_failed(self, state: dict[str, Any], exc: BaseException) -> None:
        request_id = state.get("request_id")
        if not request_id:
            return
        try:
            await ResultService(
                RequestRepository(self.session), AuditRepository(self.session)
            ).mark_status(
                state=state,
                status="failed",
                event_type="workflow_failed",
                details={"error": exc.__class__.__name__},
            )
        except Exception:
            logger.exception(
                "failed to persist workflow failure",
                extra={"path": f"/workflows/{request_id}"},
            )

    def _summary(
        self, recommendation: dict[str, Any] | None
    ) -> RecommendationSummary | None:
        if not recommendation:
            return None
        evidence_ids = [
            str(item["chunk_id"])
            for item in recommendation.get("evidence") or []
            if isinstance(item, dict) and item.get("chunk_id")
        ]
        return RecommendationSummary(
            id=recommendation.get("id"),
            supplier_id=str(recommendation["supplier_id"]),
            supplier_name=str(recommendation.get("supplier_name") or ""),
            score=str(recommendation["score"]),
            scoring_version=str(recommendation.get("scoring_version", "")),
            total_cost=str(recommendation["total_cost"]),
            unit_price=str(recommendation["unit_price"]),
            currency=str(recommendation.get("currency", "INR")),
            delivery_days=int(recommendation["delivery_days"]),
            version=int(recommendation["version"]),
            caveats=list(recommendation.get("caveats") or []),
            evidence_chunk_ids=evidence_ids,
        )

    def _recommendation_from_record(self, record: Any) -> dict[str, Any]:
        rationale = record.rationale_json or {}
        comparison = rationale.get("comparison") or {}
        supplier_name = ""
        for item in comparison.get("eligible") or []:
            if item.get("supplier_id") == record.supplier_id:
                supplier_name = str(item.get("supplier_name", ""))
                break
        evidence = (record.evidence_json or {}).get("items") or []
        return {
            "id": record.id,
            "supplier_id": record.supplier_id,
            "supplier_name": supplier_name,
            "score": str(record.score),
            "scoring_version": rationale.get("scoring_version", ""),
            "total_cost": next(
                (
                    item.get("total_cost")
                    for item in comparison.get("eligible") or []
                    if item.get("supplier_id") == record.supplier_id
                ),
                "0",
            ),
            "unit_price": next(
                (
                    item.get("unit_price")
                    for item in comparison.get("eligible") or []
                    if item.get("supplier_id") == record.supplier_id
                ),
                "0",
            ),
            "currency": comparison.get("rationale", {}).get("currency", "INR"),
            "delivery_days": next(
                (
                    item.get("delivery_days")
                    for item in comparison.get("eligible") or []
                    if item.get("supplier_id") == record.supplier_id
                ),
                0,
            ),
            "version": record.version,
            "caveats": rationale.get("caveats") or [],
            "evidence": evidence,
        }
