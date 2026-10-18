#!/bin/sh
set -eu

alembic upgrade head
python -m backend.manage_admin --from-env
python -m ml.index_content
python -m ml.index_search_content
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
