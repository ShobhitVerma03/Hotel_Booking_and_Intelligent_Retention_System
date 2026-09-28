# Docker local environment

Phase 12 runs the production-style FastAPI application, PostgreSQL, and two
separate React portals locally. It does not replace the lightweight SQLite
configuration used by unit tests.

## Prerequisites

Install Docker Desktop with Docker Compose enabled. From the repository root,
copy `.env.docker.example` to `.env` and replace each `CHANGE_ME` value. Do not
commit that `.env` file.

## Start and stop

```powershell
docker compose up --build
```

URLs:

- Customer portal: `http://localhost:${CUSTOMER_FRONTEND_PORT:-8080}`
- Manager portal: `http://localhost:${MANAGER_FRONTEND_PORT:-8081}`
- Backend health: `http://localhost:${BACKEND_PORT:-8000}/api/v1/health`
- Backend OpenAPI: `http://localhost:${BACKEND_PORT:-8000}/docs`

The included Docker environment template uses `18000`, `18080`, and `18081`
to avoid common local port collisions; change only these host-port variables
when a host port is already in use.

The frontend images use a same-origin `/api` reverse proxy to the backend. If a
portal is built for a separately hosted API, set `CUSTOMER_API_BASE_URL` or
`MANAGER_API_BASE_URL` in `.env` before building.

Stop services with `docker compose down`. Preserve database, RAG, and LangGraph
state across restarts. To intentionally remove all local container data, run
`docker compose down -v`.

## Startup and data

The backend waits by retrying Alembic migrations, applies migrations once, then
runs the existing idempotent seed operation. The configured manager account is
created or updated only through `DEV_MANAGER_EMAIL` and `DEV_MANAGER_PASSWORD`.
Room reference data is not duplicated.

Persistent named volumes are:

- `postgres_data`: PostgreSQL business data.
- `rag_data`: local Chroma policy collection.
- `langgraph_data`: workflow checkpoints.

The trusted policy PDF is copied into the backend image for server-side RAG
ingestion only. No frontend route exposes it.

## Configuration

Important settings include `DATABASE_URL`, `JWT_SECRET_KEY`, manager seed
settings, `ML_MODEL_PATH`, `RAG_*`, `LANGGRAPH_CHECKPOINT_PATH`, `GROQ_API_KEY`,
`NL_SQL_*`, and `CORS_ORIGINS`. See `.env.example` for all application settings
and `.env.docker.example` for Docker secrets. In Compose, the production-like
database URL is generated from the PostgreSQL environment values; it is not
hard-coded in source.

## Verification

```powershell
docker compose config
docker compose up --build
Invoke-RestMethod http://localhost:8000/api/v1/health
docker compose logs backend
```

Use the seeded manager credentials from your local `.env` to sign into the
manager portal. Verify a customer registration/booking and a manager dashboard,
retention decision, policy search, and NL-to-SQL analytics query.

## Troubleshooting

- If migrations keep retrying, check `docker compose logs postgres backend` and
  confirm the required PostgreSQL values are present in `.env`.
- If RAG has no collection after a clean start, the first manager policy search
  may require the existing idempotent ingestion path; inspect backend logs.
- `docker compose down` retains volumes. Use `down -v` only when intentionally
  discarding local data.
- On this Windows host, one Phase 6 regression can fail because Application
  Control blocks scikit-learn's `_gradient_boosting.cp312-win_amd64.pyd`. The
  RandomForest code and model are intentionally unchanged. This Windows policy
  limitation is not expected inside the Linux container image; do not alter the
  model merely to change the local count.
