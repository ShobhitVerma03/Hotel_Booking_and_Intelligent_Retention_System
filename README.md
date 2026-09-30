# Intelligent Hotel Booking and Retention System

The production application is a FastAPI + PostgreSQL hotel platform with
separate React customer and manager portals. It supports booking and
cancellation lifecycles, RandomForest cancellation-risk prediction, ChromaDB
policy retrieval, an explicit LangGraph recommendation workflow, persistent
manager HITL decisions, and manager-only read-only multilingual NL-to-SQL.

The legacy Flask/Streamlit prototype is retained for historical reference only;
it is not the deployment target.

## Architecture

```text
Customer React ─┐
                ├─ FastAPI ─ PostgreSQL
Manager React ──┘       ├─ RandomForest risk model
                          ├─ Chroma policy RAG
                          └─ LangGraph + manager HITL
```

ML predicts risk; RAG retrieves policy; LangGraph makes a recommendation; the
manager reviews offers requiring approval; policy-authorized medium-risk breakfast
can be published automatically. The customer accepts or rejects a
published offer. Generated SQL is manager-only, AST-validated, SELECT-only, and
read-only.

## Docker quick start

```powershell
Copy-Item .env.docker.example .env
# Replace all CHANGE_ME values in .env.
docker compose up --build
```

Default URLs: customer `http://localhost:8082`, manager
`http://localhost:8081`, API health `http://localhost:8000/api/v1/health`.
Stop while retaining volumes with `docker compose down`.

See [Docker local setup](docs/DOCKER.md), [deployment readiness](docs/DEPLOYMENT.md),
and [Jenkins CI](docs/JENKINS.md).

## Configuration and security

Copy `.env.example` for local direct development, `.env.docker.example` for
Docker, or `.env.production.example` into a platform secret manager for
production. Never commit real secrets. Production requires Alembic migrations
and a strong `JWT_SECRET_KEY`; it intentionally does not auto-create schema.

## Verification

```powershell
python -m compileall -q backend
python -m alembic -c backend/alembic.ini upgrade head
python -m unittest discover -s backend/tests -v
docker compose config --quiet
```

The local Windows ML virtual environment may be blocked by Application Control
from loading a scikit-learn native DLL. This does not justify changing the
RandomForest model; Docker/Linux is the reproducible validation path.

## Workflows and Render

The [implementation audit](docs/IMPLEMENTATION_AUDIT.md) maps the original code
and verified root causes. Cancellation has a separate explicit confirmation,
persisted manager approval/rejection, and customer status links. Returning
bookings create proactive retention requests without marking the booking as
cancelled. Low-risk policy offers are future-stay vouchers, never discounts on
the current booking. Manager screens show the exact retrieved evidence.

For local development install Docker Desktop (Linux containers). Node 22+ is
needed only for direct frontend tests/builds; Python 3.12 and the backend
requirements are needed only outside Docker. Startup applies Alembic, seeds
reference rooms/initial manager when configured, and indexes the trusted PDF.
Reindex explicitly with:

```powershell
docker compose exec -T backend python -c "from backend.app.services.rag import PolicyIngestionService; print(PolicyIngestionService().ingest_policy())"
npm --prefix frontend/customer test
npm --prefix frontend/manager test
```

The [Render guide](docs/DEPLOYMENT.md) covers GitHub, PostgreSQL, backend Docker,
two static sites, secrets, CORS, build-time API URL, migrations, health checks,
RAG rebuilds and verification. `render.yaml` selects free resources, but **free
Render PostgreSQL expires after 30 days** and the backend's **512 MB memory
limit must accommodate the full ML/RAG runtime**. Free hosting is suitable only
for a bounded demonstration if the memory probe succeeds. The bundled model
is explicitly synthetic/development-only, not validated for real guest decisions.

Never overwrite an existing `.env` when following quick start. If an existing
PostgreSQL volume reports a missing database, restore the database name that
was used when the volume was initialized; changing POSTGRES_DB does not rename
an existing database. Do not delete the volume to fix configuration.
