# Render deployment and operating guide

## Honest free-tier scope

This is a four-resource deployment, not Docker Compose on Render:

- `frontend/customer`: Render Static Site, Vite React.
- `frontend/manager`: separate Render Static Site, Vite React.
- Repository root / `backend/Dockerfile`: Docker Web Service running FastAPI.
- Render PostgreSQL: application records, offers, decisions and workflow snapshots.

The blueprint selects free plans explicitly. This is a demonstration deployment,
not a claim of permanent free production hosting. Render's free PostgreSQL expires
30 days after creation, has 1 GB storage and no backups. Free web services have
512 MB RAM, sleep after 15 minutes idle, share 750 monthly instance hours, and
cannot attach persistent disks. Free static sites are subject to workspace usage
limits. Cold starts and RAG ingestion can delay availability. The existing
PyTorch/MiniLM + Chroma + pandas/scikit-learn backend must pass the memory check
below; if it exceeds 512 MB, the full preserved architecture cannot run reliably
on that free service. Do not disable RAG/ML to conceal that failure.

Sources checked 2026-09-29: [Render free limits](https://render.com/docs/free),
[compute plans](https://render.com/docs/compute-plans),
[Blueprint schema](https://render.com/docs/blueprint-spec).

## Provision from GitHub

1. Review `git diff`, run tests, commit intended source changes, and push to your
   GitHub repository. Never add `.env`, logs, database files or credentials.
2. In Render choose New Blueprint and connect the repository containing
   `render.yaml`. Review the free resource selections before creating anything.
   Alternatively create the four resources manually with the settings below.
3. Keep PostgreSQL and backend in the same region (blueprint: Singapore). The
   backend obtains the internal connection string through `fromDatabase`.
   External database access is disabled by the blueprint's empty IP allowlist.
4. Configure the two actual static-site HTTPS origins in backend `CORS_ORIGINS`,
   comma separated, with no trailing slash or path. For example:
   `https://your-customer.onrender.com,https://your-manager.onrender.com`.
5. Set each site's `VITE_API_BASE_URL` to the backend's actual HTTPS origin, e.g.
   `https://your-api.onrender.com`. No secret belongs in a VITE variable.
   Clients also tolerate a versioned `/api/v1` suffix, but prefer the origin.
   Rebuild the static sites after changing this build-time variable.
6. Configure an initial `DEV_MANAGER_EMAIL` and strong `DEV_MANAGER_PASSWORD`
   through Render's environment UI. `SEED_DATABASE=true` inserts the initial
   manager and sample room inventory idempotently. Replace sample room data with
   approved hotel inventory before real use. Set `SEED_DATABASE=false` after
   bootstrap; never enable `RESET_SEED_MANAGER_PASSWORD` for routine deploys.
7. The blueprint generates a JWT secret. Keep it stable across deploys. Optional
   `GROQ_API_KEY` is needed only with `NL_SQL_LLM_ENABLED=true`. Tavily and
   LangChain tracing keys belong to the retained legacy prototype, not this
   backend's normal booking/retention pipeline.

## Exact service settings

Backend: Dockerfile `backend/Dockerfile`, context `.`, no rootDir, no overridden
Docker command. Entry point runs Alembic, optional seeding, deterministic RAG
initialization, then binds Uvicorn to `0.0.0.0:$PORT` (8000 locally). Health path
`/api/v1/health` checks PostgreSQL and returns 503 when unavailable. Root `/`
is not an API endpoint; `/docs` provides API documentation.

Static sites: rootDir `frontend/customer` and `frontend/manager` respectively;
build command `npm ci && npm run build`; publish directory `dist`; rewrite
`/*` to `/index.html`. Their Docker nginx API proxies apply only locally.
Render static sites call the backend directly through the configured HTTPS URL.

Required backend values: `APP_ENV=production`, `DATABASE_URL` from Render,
`JWT_SECRET_KEY`, `CORS_ORIGINS`, `AUTO_CREATE_SCHEMA=false`.
Postgres URLs are normalized to the installed psycopg driver. URL-encode reserved
characters when constructing a connection string yourself. Production rejects
SQLite, wildcard/local CORS and missing/placeholder JWT secrets.

Other settings and placeholders are listed in `.env.production.example` and
`backend/app/core/config.py`. Never print the live environment during diagnostics.

## Persistence and initialization

PostgreSQL is authoritative for customers, bookings, cancellation requests,
retention decisions, offers, audit records and full workflow snapshots. Migration
`20260929_0003` adds request origin and JSON workflow state without deleting rows.
Startup applies `alembic -c /app/backend/alembic.ini upgrade head` because free
web services do not offer the same deployment-job/shell facilities as paid plans.

The PDF `data/policy/Company_Retention_Policy_2026.pdf`, trusted RandomForest
artifact and real MiniLM model are bundled in the backend image. Chroma is a
rebuildable cache under `/tmp/hotel-rag`. Startup normalizes PDF whitespace,
chunks, embeds and upserts. A policy/config fingerprint avoids redundant
embedding on unchanged local volumes. Stale chunk IDs are removed after reindex.
Missing PDF/model/index raises an error; no invented evidence is substituted.

SQLite LangGraph execution checkpoints under `/tmp/hotel-workflow` are disposable.
Final and pending workflow state is committed to PostgreSQL with the business
transaction and reused after restart. In-flight work can be rerun from the saved
request; manager decisions and accepted offers are not duplicated. Before
upgrading an older installation, finish outstanding old SQLite-only reviews or
regenerate them with the new code so they have PostgreSQL snapshots.

No uploaded file storage is implemented. Do not use ephemeral disk for future
uploads or retrain the development model automatically on application startup.

## Verification commands

Local Windows/PowerShell (Docker Desktop running):

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose exec -T backend python -m alembic -c /app/backend/alembic.ini current
docker compose exec -T backend python -m unittest discover -s backend/tests -v
npm --prefix frontend/customer test
npm --prefix frontend/manager test
npm --prefix frontend/customer run build
npm --prefix frontend/manager run build
```

Use an isolated test container for unit tests if you do not want test index files
in the running container:

```powershell
docker run --rm --entrypoint python intelligent-hotel-retention-agent-v2-main-backend -m unittest discover -s backend/tests -v
```

Memory probe preserving actual ML/RAG:

```powershell
docker run --rm --memory=512m --memory-swap=512m --entrypoint python intelligent-hotel-retention-agent-v2-main-backend -c "from backend.app.services.rag import PolicyIngestionService,PolicyRAGService; from backend.ml.predict import load_model; PolicyIngestionService().ingest_policy(); load_model(); print(len(PolicyRAGService().retrieve_policy('low-risk future-stay voucher')))"
```

An OOM/exit 137 is a release blocker for the free backend. Use a compute plan
with sufficient memory, or explicitly scope and validate a separate memory
optimization project. No paid resources are provisioned by these instructions.
For lasting PostgreSQL persistence, upgrade/export before day 30; a free Render
Postgres instance is not an indefinite database solution.

After deployment verify `/api/v1/health`, `/docs`, both SPA deep links, valid and
invalid logins, cross-customer 404/403, customer → cancellation confirmation →
manager approve/reject → customer refresh, and second booking → real policy
recommendation → automatic benefit or manager decision → customer response.
Verify a CORS preflight from each frontend and rejection of an unrelated origin.
Test a backend restart with a pending manager review to confirm persistence.

The supplied RandomForest is **synthetic development only** (`synthetic-dev-v1`).
Successful inference is not evidence of production predictive accuracy. Before
using risk scores for real guests, train/evaluate against authorized historical
outcomes with time-based validation and capture currently unknown hotel/payment
attributes. No production labels have been fabricated.
