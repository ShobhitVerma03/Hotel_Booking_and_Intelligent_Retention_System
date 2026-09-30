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

- Customer portal: `http://localhost:8082` by default
- Manager portal: `http://localhost:8081` by default
- Backend health: `http://localhost:8000/api/v1/health` by default
- Backend OpenAPI: `http://localhost:8000/docs` by default

The included Docker environment template uses `8000`, `8082`, and `8081`
to avoid common local port collisions; change only these host-port variables
when a host port is already in use.

The frontend images use a same-origin `/api` reverse proxy to the backend. If a
portal is built for a separately hosted API, set `CUSTOMER_API_BASE_URL` or
`MANAGER_API_BASE_URL` in `.env` before building.

Stop services with `docker compose down`. Preserve database, RAG, and LangGraph
state across restarts. To intentionally remove all local container data, run
`docker compose down -v`.

## Startup and data

The backend waits by retrying Alembic migrations and applies only unapplied
migrations. It runs the idempotent seed operation only when `SEED_DATABASE=true`.
The configured manager account is created when absent; its password changes only
when `RESET_SEED_MANAGER_PASSWORD=true`. Room reference data is not duplicated.

Persistent named volumes are:

- `postgres_data`: PostgreSQL business data.
- `rag_data`: local Chroma policy collection.
- `langgraph_data`: workflow checkpoints.

The project-owned policy PDF is copied into the backend image for server-side
RAG ingestion only. No frontend route exposes it. The persistent RAG volume
keeps the Chroma collection across restarts; ingestion uses stable IDs.

## Configuration

Important settings include `DATABASE_URL`, `JWT_SECRET_KEY`, manager seed
settings, `ML_MODEL_PATH`, `RAG_*`, `LANGGRAPH_CHECKPOINT_PATH`, `GROQ_API_KEY`,
`NL_SQL_*`, and `CORS_ORIGINS`. See `.env.example` for all application settings
and `.env.docker.example` for Docker secrets. In Compose, the production-like
database URL is generated from the PostgreSQL environment values; it is not
hard-coded in source.

## Verification

```powershell
docker compose config --quiet
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
  fails startup clearly; inspect backend logs and rerun the documented ingestion command.
- `docker compose down` retains volumes. Use `down -v` only when intentionally
  discarding local data.
- On this Windows host, one Phase 6 regression can fail because Application
  Control blocks scikit-learn's `_gradient_boosting.cp312-win_amd64.pyd`. The
  RandomForest code and model are intentionally unchanged. This Windows policy
  limitation is not expected inside the Linux container image; do not alter the
  model merely to change the local count.
