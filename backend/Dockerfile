FROM python:3.12-slim AS base

ARG INSTALL_EMBEDDINGS=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app
WORKDIR /app

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY ml/requirements.txt /tmp/ml-requirements.txt
RUN if [ "$INSTALL_EMBEDDINGS" = "true" ]; then \
    pip install --no-cache-dir 'torch>=2.6,<3' --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r /tmp/ml-requirements.txt; \
    fi

COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY backend/ ./backend/
COPY ml/ ./ml/

FROM base AS runtime
USER 10001:10001
EXPOSE 8000
CMD ["sh", "/app/backend/entrypoint.sh"]
