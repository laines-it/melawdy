FROM python:3.12-slim AS base

ARG DOWNLOAD_EMBEDDING_MODEL=false
ARG EMBEDDINGS_ENABLED=true
ARG IMPORT_FEES=true
ARG IMPORT_DOCUMENT_TEMPLATES=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HF_HOME=/opt/hf-cache \
    EMBEDDINGS_ENABLED=$EMBEDDINGS_ENABLED \
    IMPORT_FEES=$IMPORT_FEES \
    IMPORT_DOCUMENT_TEMPLATES=$IMPORT_DOCUMENT_TEMPLATES
WORKDIR /app

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY ml/requirements.txt /tmp/ml-requirements.txt
RUN if [ "$EMBEDDINGS_ENABLED" = "true" ]; then \
    pip install --no-cache-dir 'torch>=2.6,<3' --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r /tmp/ml-requirements.txt; \
    fi

COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY backend/ ./backend/
COPY docs/examples/ ./docs/examples/
COPY ml/ ./ml/
COPY music_plagiarism/colab/ ./music_plagiarism/colab/
RUN if [ "$EMBEDDINGS_ENABLED" = "true" ] && [ "$DOWNLOAD_EMBEDDING_MODEL" = "true" ]; then \
    python -m ml.download_model --output-dir /opt/embedding-model; \
    fi

# Windows checkouts may contain CRLF, including in existing working copies.
RUN python -c "from pathlib import Path; p = Path('backend/entrypoint.sh'); p.write_bytes(p.read_bytes().replace(b'\r\n', b'\n'))"

FROM base AS runtime
RUN mkdir -p /opt/hf-cache /var/lib/melawdy/music-check && chown 10001:10001 /opt/hf-cache /var/lib/melawdy/music-check
USER 10001:10001
EXPOSE 8000
CMD ["sh", "/app/backend/entrypoint.sh"]
