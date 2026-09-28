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
manager makes the hotel-side decision; the customer later accepts or rejects a
published offer. Generated SQL is manager-only, AST-validated, SELECT-only, and
read-only.

## Docker quick start

```powershell
Copy-Item .env.docker.example .env
# Replace all CHANGE_ME values in .env.
docker compose up --build
```

Default URLs: customer `http://localhost:18080`, manager
`http://localhost:18081`, API health `http://localhost:18000/api/v1/health`.
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
