FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app
WORKDIR /app

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY backend/ ./backend/
COPY ml/ ./ml/

FROM base AS runtime
USER 10001:10001
EXPOSE 8000
CMD ["sh", "/app/backend/entrypoint.sh"]
