# Deployment readiness

This repository is prepared for deployment but does not provision cloud
accounts, DNS, or a hosted environment. Production deployment remains a manual
operator task.

## Configuration

Copy `.env.production.example` into a secret manager or untracked environment
file and replace every `CHANGE_ME` value. Required values include PostgreSQL
`DATABASE_URL`, a strong `JWT_SECRET_KEY`, exact `CORS_ORIGINS`, and optional
LLM provider keys. Keep `SEED_DATABASE=false` on an existing production
database. If seeding an initial manager, keep
`RESET_SEED_MANAGER_PASSWORD=false` so ordinary restarts never rotate it.

For each separately hosted frontend, set build-time `VITE_API_BASE_URL` to the
public API versioned base URL, such as `https://api.example.com/api/v1`. An empty
value is only correct for Docker's same-origin `/api` proxy.

## Fresh PostgreSQL database

1. Provision a least-privilege PostgreSQL application user and database.
2. Configure the production environment.
3. Apply migrations before serving traffic:

   ```powershell
   python -m alembic -c backend/alembic.ini upgrade head
   ```

4. To seed reference data and an initial manager, temporarily set
   `SEED_DATABASE=true`, run `python -m backend.app.database.initialize`, then
   set it back to `false`.

Production does not auto-create schema; `AUTO_CREATE_SCHEMA` must stay false.

## Persistence

The Docker backend bundles the approved policy PDF and RandomForest artifact.
Attach durable storage to `RAG_PERSIST_DIRECTORY` and
`LANGGRAPH_CHECKPOINT_PATH`; without it a restart loses Chroma policy data and
workflow checkpoints. Policy ingestion is idempotent with stable chunk IDs.
The PDF is server-side only and has no public route.

## Intended hosted topology

- Customer React frontend: Vercel or equivalent static host.
- Manager React frontend: separate Vercel or equivalent project.
- FastAPI backend: Render or an equivalent container host.
- Business database: Neon PostgreSQL or equivalent managed PostgreSQL.
- RAG and checkpoints: durable storage supported by the backend host.

Check a provider's current plan limits, persistence, sleep behavior, and secret
support directly before selecting it. No cloud deployment URL is claimed here.

## Release checklist

- Run Alembic on a clean PostgreSQL database.
- Inject secrets through the deployment platform, never Git.
- Configure HTTPS origins in `CORS_ORIGINS`.
- Configure both frontends with the HTTPS API URL.
- Mount persistent RAG and LangGraph storage.
- Validate health, auth, booking/cancellation, risk, RAG, HITL, and NL-to-SQL.
- Review Jenkins CI output; CI validation is not deployment.

## Known limitation

Local Windows `.venv-ml` tests can be blocked by Application Control loading a
scikit-learn native DLL. RandomForest remains unchanged; Docker/Linux is the
reproducible verification path.
