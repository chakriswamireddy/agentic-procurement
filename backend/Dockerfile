# syntax=docker/dockerfile:1
# Multi-stage, non-root backend image (Phase 6, Step 6.10).

FROM python:3.12.8-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken_cache \
    FASTEMBED_CACHE_DIR=/opt/fastembed_cache

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')" \
    && python -c "from fastembed import TextEmbedding, SparseTextEmbedding; list(TextEmbedding('BAAI/bge-small-en-v1.5').embed(['warmup'])); list(SparseTextEmbedding('Qdrant/bm25').embed(['warmup']))"


FROM python:3.12.8-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    FASTEMBED_CACHE_DIR=/home/app/.cache/fastembed \
    TIKTOKEN_CACHE_DIR=/home/app/.cache/tiktoken \
    HOME=/home/app

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --create-home app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=app:app /opt/tiktoken_cache /home/app/.cache/tiktoken
COPY --from=builder --chown=app:app /opt/fastembed_cache /home/app/.cache/fastembed
WORKDIR /app
COPY --chown=app:app app ./app

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).status == 200 else 1)"

# One worker is the documented local/production-like default. Scale with replicas
# (Cloud Run / Compose scale) rather than in-process workers that share a process-local
# Redis client and checkpointer pool.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
