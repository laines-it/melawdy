#!/bin/sh
set -eu

alembic upgrade head
if [ "${IMPORT_DOCUMENT_TEMPLATES:-false}" = "true" ]; then
    python -m backend.import_template /app/docs/examples/coauthors-template.json
fi
if [ "${IMPORT_FEES:-true}" = "true" ]; then
    python -m backend.import_fees
fi
python -m backend.manage_admin --from-env
embeddings_enabled=$(python -c 'from backend.config import get_settings; print(int(get_settings().embeddings_enabled))')
if [ "$embeddings_enabled" = "1" ]; then
    python -m ml.index_content
    python -m ml.index_search_content
else
    echo "Embeddings disabled; search uses BM25"
fi
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
