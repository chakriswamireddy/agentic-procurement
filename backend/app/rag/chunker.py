"""Section-aware, token-bounded policy chunker.

Token counts use ``tiktoken``'s ``cl100k_base`` encoding as a documented
approximation. The embedding model (``bge-small-en-v1.5``) uses a different
tokenizer, so the 350-token target deliberately leaves headroom below its
512-token limit.

Each chunk text is prefixed with ``[Section: ...]`` so that the embedded text
carries its heading context. The same heading is also stored in ``section_path``
for citations and filtering.
"""

import hashlib
import re
import uuid
from dataclasses import dataclass, field

import tiktoken

from app.rag.document_loader import LoadedDocument

_ENCODER = tiktoken.get_encoding("cl100k_base")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_UNIT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
MAX_OVERLAP_RATIO = 0.2
_CHUNK_NAMESPACE = uuid.NAMESPACE_URL


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_ENCODER.encode(text))


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    version: str
    section_path: str
    chunk_index: int
    text: str
    token_count: int
    hard_split: bool = field(default=False)


def _section_text(section_path: str) -> str:
    return f"[Section: {section_path}]\n\n" if section_path else ""


def _tail_tokens(text: str, overlap_tokens: int) -> str:
    if overlap_tokens <= 0 or not text:
        return ""
    tokens = _ENCODER.encode(text)
    for size in range(min(overlap_tokens, len(tokens)), 0, -1):
        candidate = _ENCODER.decode(tokens[-size:]).strip()
        if candidate and count_tokens(candidate) <= overlap_tokens:
            return candidate
    return ""


def _split_to_budget(text: str, budget: int) -> list[str]:
    """Split a single oversized unit on word boundaries into budget-sized pieces."""
    if budget <= 0:
        return []
    if count_tokens(text) <= budget:
        return [text]

    words = text.split()
    pieces: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and count_tokens(candidate) > budget:
            pieces.append(" ".join(current))
            current = [word]
        else:
            current.append(word)

    if current:
        pieces.append(" ".join(current))

    # A pathological single word can still exceed the budget. Cut its tokens.
    safe_pieces: list[str] = []
    for piece in pieces:
        token_ids = _ENCODER.encode(piece)
        if len(token_ids) <= budget:
            safe_pieces.append(piece)
            continue
        for start in range(0, len(token_ids), budget):
            safe_pieces.append(_ENCODER.decode(token_ids[start : start + budget]).strip())
    return [piece for piece in safe_pieces if piece]


def _blocks_with_sections(body: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    headings: list[tuple[int, str]] = []
    buffer: list[str] = []

    def section_path() -> str:
        return " > ".join(title for _, title in headings)

    def flush() -> None:
        if buffer:
            text = "\n".join(buffer).strip()
            if text:
                blocks.append((section_path(), text))
            buffer.clear()

    for line in body.splitlines():
        match = _HEADING_RE.match(line.strip())
        if match:
            flush()
            level = len(match.group(1))
            title = match.group(2).strip()
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, title))
            continue
        if not line.strip():
            flush()
            continue
        buffer.append(line.rstrip())
    flush()
    return blocks


def _units(text: str) -> list[str]:
    return [unit.strip() for unit in _UNIT_SPLIT_RE.split(text) if unit.strip()]


def chunk_document(
    doc: LoadedDocument,
    *,
    target_tokens: int = 350,
    overlap_tokens: int = 50,
) -> list[Chunk]:
    if target_tokens <= 0:
        raise ValueError("target_tokens must be positive")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens must not be negative")

    bounded_overlap = min(overlap_tokens, int(target_tokens * MAX_OVERLAP_RATIO))
    chunks: list[Chunk] = []
    chunk_index = 0

    for section_path, block in _blocks_with_sections(doc.body):
        prefix = _section_text(section_path)
        prefix_tokens = count_tokens(prefix)
        budget = max(target_tokens - prefix_tokens, 1)

        units: list[tuple[str, bool]] = []
        for unit in _units(block):
            if count_tokens(unit) > budget:
                units.extend((piece, True) for piece in _split_to_budget(unit, budget))
            else:
                units.append((unit, False))
        if not units:
            continue

        current: list[str] = []
        current_hard_split = False
        has_new_content = False
        overlap = ""

        def build_text(parts: list[str], prefix: str = prefix) -> str:
            return f"{prefix}{' '.join(parts)}".strip()

        def emit(section_path: str = section_path) -> None:
            nonlocal chunk_index, current, current_hard_split
            nonlocal has_new_content, overlap
            if not current or not has_new_content:
                return

            text = build_text(current)
            token_count = count_tokens(text)
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            name = f"{doc.document_id}|{doc.version}|{section_path}|{chunk_index}|{digest}"
            chunks.append(
                Chunk(
                    chunk_id=str(uuid.uuid5(_CHUNK_NAMESPACE, name)),
                    document_id=doc.document_id,
                    version=doc.version,
                    section_path=section_path,
                    chunk_index=chunk_index,
                    text=text,
                    token_count=token_count,
                    hard_split=current_hard_split,
                )
            )
            chunk_index += 1
            overlap = _tail_tokens(" ".join(current), bounded_overlap)
            current = [overlap] if overlap else []
            current_hard_split = False
            has_new_content = False

        for unit, hard_split in units:
            candidate = build_text([*current, unit])
            if current and has_new_content and count_tokens(candidate) > budget:
                emit()
                candidate = build_text([*current, unit])
                if current and count_tokens(candidate) > budget:
                    current = []
                    candidate = build_text([unit])

            current.append(unit)
            current_hard_split = current_hard_split or hard_split
            has_new_content = True

        emit()

    return chunks
