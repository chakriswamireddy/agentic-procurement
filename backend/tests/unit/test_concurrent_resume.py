"""Unit test verifying concurrent resume race condition mitigation (Phase 5 idempotency gap)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.config import Settings
from app.core.errors import ConflictError
from app.services.workflow_service import WorkflowService


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        jwt_secret="super-secret-jwt-key-with-sufficient-length-32bytes",
        database_url="postgresql://procurement:procurement@localhost:5432/procurement",
        mongodb_url="mongodb://localhost:27017",
    )


@pytest.mark.asyncio
async def test_concurrent_resume_race_raises_conflict(mock_settings: Settings) -> None:
    session = AsyncMock()
    mongo_db = MagicMock()
    policy_service = MagicMock()
    graph = AsyncMock()

    # Model request record
    mock_request = MagicMock()
    mock_request.status = "awaiting_approval"

    # Simulate lock_for_resume:
    # First caller gets row in awaiting_approval status and changes it to resuming.
    # Second caller sees status == 'resuming' and raises ConflictError.
    calls = 0

    async def mock_execute(statement):
        nonlocal calls
        calls += 1
        result = MagicMock()
        if calls == 1:
            result.scalar_one_or_none.return_value = mock_request
        else:
            conflict_request = MagicMock()
            conflict_request.status = "resuming"
            result.scalar_one_or_none.return_value = conflict_request
        return result

    session.execute = mock_execute

    service = WorkflowService(
        mock_settings,
        graph,
        session=session,
        mongo_db=mongo_db,
        policy_service=policy_service,
    )

    # First call succeeds
    snapshot = MagicMock()
    snapshot.values = {"status": "awaiting_approval", "request_id": "PRQ-123"}
    snapshot.next = ("approval_interrupt",)
    graph.aget_state.return_value = snapshot
    graph.ainvoke.return_value = {"status": "executed", "request_id": "PRQ-123"}

    service.get_status = AsyncMock()

    # Run resume 1
    await service.resume("PRQ-123", {"decision": "approved", "approver_id": "USR0005"})

    # Run concurrent resume 2 - MUST raise ConflictError
    with pytest.raises(ConflictError, match="workflow is not awaiting approval"):
        await service.resume("PRQ-123", {"decision": "approved", "approver_id": "USR0005"})
