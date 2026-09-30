#!/bin/sh
set -eu

# Alembic itself is the database readiness check: it retries while PostgreSQL
# starts, then applies only unapplied migrations.  No schema is recreated.
attempt=1
until alembic -c /app/backend/alembic.ini upgrade head; do
  if [ "$attempt" -ge 30 ]; then
    echo "Database migrations did not become available after 30 attempts." >&2
    exit 1
  fi
  attempt=$((attempt + 1))
  echo "Waiting for database before retrying migrations ($attempt/30)..." >&2
  sleep 2
done

# Seed records and the configured development manager are inserted idempotently.
python -m backend.app.database.initialize

# The container-owned Chroma volume starts empty on its first run.  Populate it
# from the trusted, image-bundled policy using stable IDs/upserts so subsequent
# starts neither delete nor duplicate the policy collection.
python -c "from backend.app.services.rag import PolicyIngestionService; PolicyIngestionService().ingest_policy()"
if [ "$#" -eq 0 ]; then
  set -- uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
fi
exec "$@"
