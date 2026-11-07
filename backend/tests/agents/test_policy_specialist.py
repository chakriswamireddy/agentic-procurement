"""Policy specialist: evidence, inconclusive signalling, and error mapping (step 4.4)."""

from datetime import date
from types import SimpleNamespace

from app.agents.contracts import PermanentError, PolicyQuery, TransientError
from app.agents.policy_specialist import PolicySpecialist

AS_OF = "2026-01-15"


def make_query(**overrides) -> PolicyQuery:
    values = {"text": "procurement approval threshold", "as_of": AS_OF, "limit": 5}
    values.update(overrides)
    return PolicyQuery(**values)


def make_chunk(chunk_id: str = "chunk-0001", **overrides) -> dict:
    chunk = {
        "chunk_id": chunk_id,
        "document_id": "POL-001",
        "version": "3.2",
        "title": "Procurement Policy",
        "section_path": "4.1 Thresholds",
        "text": "Purchases above threshold require approval.",
        "score": 0.05,
        "dense_rank": 1,
        "sparse_rank": 1,
        "source_path": "data/documents/policy-001.md",
        "effective_from": "2026-01-01",
        "status": "active",
        "classification": "internal",
        "injection_suspected": False,
    }
    chunk.update(overrides)
    return chunk


class FakePolicyPort:
    def __init__(self, evidence=None, inconclusive=False, reason=None, error=None):
        self.evidence = evidence if evidence is not None else [make_chunk()]
        self.inconclusive = inconclusive
        self.reason = reason
        self.error = error
        self.calls: list[dict] = []

    async def search(
        self,
        query,
        *,
        limit=None,
        as_of=None,
        classifications=None,
        document_ids=None,
        mode="hybrid",
    ):
        self.calls.append(
            {
                "query": query,
                "limit": limit,
                "as_of": as_of,
                "classifications": classifications,
                "document_ids": document_ids,
                "mode": mode,
            }
        )
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            query=query,
            inconclusive=self.inconclusive,
            reason=self.reason,
            evidence=list(self.evidence),
        )


async def test_returns_evidence_with_source_metadata() -> None:
    specialist = PolicySpecialist(FakePolicyPort())

    result = await specialist.retrieve(make_query())

    assert result.inconclusive is False
    assert result.source_ids == ("chunk-0001",)
    evidence = result.evidence[0]
    assert evidence.document_id == "POL-001"
    assert evidence.version == "3.2"
    assert evidence.section_path == "4.1 Thresholds"
    assert evidence.score == 0.05


async def test_obsolete_and_draft_evidence_are_excluded() -> None:
    port = FakePolicyPort(
        evidence=[
            make_chunk("chunk-active", status="active"),
            make_chunk("chunk-obsolete", status="obsolete"),
            make_chunk("chunk-draft", status="draft"),
        ]
    )
    specialist = PolicySpecialist(port)

    result = await specialist.retrieve(make_query())

    assert result.source_ids == ("chunk-active",)


async def test_empty_result_is_inconclusive_not_an_error() -> None:
    specialist = PolicySpecialist(
        FakePolicyPort(evidence=[], inconclusive=True, reason="no_results")
    )

    result = await specialist.retrieve(make_query())

    assert result.inconclusive is True
    assert result.reason == "no_results"
    assert result.evidence == ()
    assert result.source_ids == ()


async def test_index_failure_maps_to_transient_error() -> None:
    specialist = PolicySpecialist(FakePolicyPort(error=ConnectionError("qdrant down")))

    try:
        await specialist.retrieve(make_query())
    except TransientError as exc:
        assert exc.code == "policy_index_unavailable"
        assert exc.transient is True
    else:
        raise AssertionError("expected a TransientError")


async def test_invalid_query_is_permanent() -> None:
    port = FakePolicyPort()
    specialist = PolicySpecialist(port)

    try:
        await specialist.retrieve(make_query(text="  "))
    except PermanentError as exc:
        assert exc.code == "invalid_policy_query"
    else:
        raise AssertionError("expected a PermanentError")
    assert port.calls == []


async def test_evidence_without_chunk_id_is_rejected() -> None:
    specialist = PolicySpecialist(
        FakePolicyPort(evidence=[{"document_id": "POL-001", "text": "no id here"}])
    )

    try:
        await specialist.retrieve(make_query())
    except PermanentError as exc:
        assert exc.code == "invalid_policy_evidence"
    else:
        raise AssertionError("expected a PermanentError")


async def test_filters_and_limit_reach_the_port() -> None:
    port = FakePolicyPort()
    specialist = PolicySpecialist(port, max_evidence=3)

    await specialist.retrieve(
        make_query(
            classifications=("internal",),
            document_ids=("POL-001",),
            limit=10,
        )
    )

    call = port.calls[0]
    assert call["as_of"] == date(2026, 1, 15)
    assert call["classifications"] == ("internal",)
    assert call["document_ids"] == ("POL-001",)
    # The specialist never asks the port for more than its own evidence budget.
    assert call["limit"] == 3
    assert call["mode"] == "hybrid"
