from datetime import date

from app.rag.chunker import _tail_tokens, chunk_document, count_tokens
from app.rag.document_loader import LoadedDocument


def make_document(body: str) -> LoadedDocument:
    return LoadedDocument(
        document_id="TST-001",
        title="Test Policy",
        version="1.0",
        status="active",
        classification="internal",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        body=body,
        source_path="data/documents/test.md",
        checksum="0" * 64,
    )


def test_section_paths_follow_heading_hierarchy() -> None:
    document = make_document(
        """
# Policy

## 1 Scope

Text one.

### 1.1 Detail

Detail text.

## 2 Approval

Approval text.
"""
    )

    chunks = chunk_document(document, target_tokens=100, overlap_tokens=10)

    assert [chunk.section_path for chunk in chunks] == [
        "Policy > 1 Scope",
        "Policy > 1 Scope > 1.1 Detail",
        "Policy > 2 Approval",
    ]
    assert all(chunk.chunk_index == index for index, chunk in enumerate(chunks))


def test_no_chunk_exceeds_token_budget() -> None:
    paragraph = " ".join(
        f"Sentence number {index} explains the policy rule." for index in range(80)
    )
    document = make_document(f"# Policy\n\n## 1 Rules\n\n{paragraph}\n")

    chunks = chunk_document(document, target_tokens=50, overlap_tokens=10)

    assert len(chunks) > 1
    assert all(count_tokens(chunk.text) <= 50 for chunk in chunks)


def test_overlap_is_present_and_bounded() -> None:
    paragraph = " ".join(
        f"Sentence {index} explains a distinct procurement requirement." for index in range(40)
    )
    document = make_document(f"# Policy\n\n## 1 Rules\n\n{paragraph}\n")

    chunks = chunk_document(document, target_tokens=60, overlap_tokens=12)
    first_content = chunks[0].text.split("\n\n", 1)[1]
    second_content = chunks[1].text.split("\n\n", 1)[1]
    overlap_text = _tail_tokens(first_content, 12)

    assert overlap_text
    assert second_content.startswith(overlap_text)
    assert count_tokens(overlap_text) <= 12


def test_chunk_ids_are_stable() -> None:
    document = make_document("# Policy\n\n## 1 Rules\n\n" + "Rule text. " * 100)

    first = chunk_document(document, target_tokens=80, overlap_tokens=10)
    second = chunk_document(document, target_tokens=80, overlap_tokens=10)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert len({chunk.chunk_id for chunk in first}) == len(first)


def test_oversized_paragraph_is_hard_split_not_dropped() -> None:
    document = make_document("# Policy\n\n## 1 Long\n\n" + "word " * 2000)

    chunks = chunk_document(document, target_tokens=100, overlap_tokens=20)

    assert len(chunks) > 1
    assert any(chunk.hard_split for chunk in chunks)
    assert all(count_tokens(chunk.text) <= 100 for chunk in chunks)


def test_empty_section_produces_no_chunk() -> None:
    document = make_document(
        "# Policy\n\n## Empty\n\n## Filled\n\nSome policy text.\n"
    )

    chunks = chunk_document(document, target_tokens=100, overlap_tokens=10)

    assert [chunk.section_path for chunk in chunks] == ["Policy > Filled"]


def test_chunk_text_includes_section_prefix() -> None:
    document = make_document("# Policy\n\n## 1 Rules\n\nSome policy text.\n")

    chunks = chunk_document(document, target_tokens=100, overlap_tokens=10)

    assert chunks[0].text.startswith("[Section: Policy > 1 Rules]")
