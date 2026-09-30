# Implementation audit — 2026-09-29 (before fixes)

## Deployment and architecture map

The deployable system is `backend/app` (FastAPI), `backend/ml` (scikit-learn
Pipeline / RandomForest), and two Vite React SPAs. Root `src`, Flask/Streamlit
entrypoints and notebooks are a separate legacy prototype, not imported by the
Docker application. They are preserved. Docker uses PostgreSQL 16, nginx SPA
fallback and `/api` proxies, image-bundled model/PDF/embedding model, Alembic,
optional idempotent room/manager seeding, then policy ingestion before Uvicorn.
Jenkins builds/tests Docker and both SPAs and runs an isolated Compose smoke test.

## Traced workflows

- Registration/login → auth API → bcrypt/JWT → users/customers. Dependencies
  load the database user and enforce manager role or customer ownership.
- Booking → customer Book → POST bookings → room overlap/capacity checks →
  bookings plus first-time welcome offer. Subsequent bookings do not invoke
  retention at all.
- Cancellation → BookingDetail confirmation → cancellation API →
  `cancel_pending` booking + pending RetentionRequest. Confirmation already
  exists in source. Manager cancellation list/resolution also already exists.
- Retention → manager recommendation endpoint → LangGraph load_context → ML
  → Chroma retrieval → deterministic policy parsing → AWAITING_MANAGER. Decision
  API writes RetentionDecision and Offer. Customer offer route exists but is
  not linked from booking details; offer response is explicitly unimplemented.
- ML → customer_features → saved preprocessing/RandomForest → thresholds
  0.40/0.70. Artifact metadata explicitly says SYNTHETIC_DEVELOPMENT.
- RAG → seven-page trusted PDF → raw character chunks → real MiniLM embeddings
  → Chroma cosine search → provenance. Startup always re-embeds. Stable IDs
  upsert but do not remove stale chunks after policy shortening.

## Verified problems

1. Local backend repeatedly fails migrations because configured database
   `hotel_retention` does not exist in the existing volume. Customer container
   absent; manager container predates current source. Preserve volume.
2. Features exclude CANCEL_PENDING, choose an unordered last history item,
   include current values in previous averages and hardcode lead time/tenure.
3. No proactive second-booking request. Existing request conflates cancellation
   and retention; distinguish origin while reusing its enums/relationships.
4. SQLite is the only saved workflow snapshot. Pending recommendations can be
   lost on ephemeral hosts; relational recommendation populated only at decision.
5. Customer cannot discover request/offer from booking, see rejection clearly,
   or accept/reject an offer. Retention rejection can strand cancel_pending.
6. Policy PDF extraction contains excessive whitespace. Section 5.1 permits a
   5% FUTURE voucher, forbids current discount; 5.2 permits complimentary
   breakfast for up to two and explicitly says no approval required; 5.3 caps
   standard rate discounts at 15%, with tier enhancements. Existing parser
   partly handles low-risk voucher, but retrieval is unscoped and medium risk
   assumes authorization without verifying text. Graph has no automatic branch.
7. Frontend deployment guide says append /api/v1 although clients append it
   themselves. Render URL scheme needs psycopg normalization; PORT ignored.
   Production settings allow SQLite/default localhost CORS. Compose defaults
   customer to 8080 while requested/local intended port is 8082.
8. Free Render has ephemeral disk, 512 MB web-service memory and a 30-day
   PostgreSQL expiry. Permanent free production hosting cannot be promised.
9. Existing tests cover auth, booking, ML, real RAG, graph and HITL but omit
   proactive second booking, ephemeral checkpoint recovery and offer completion.

## Fix approach

Keep FastAPI, PostgreSQL, RandomForest, MiniLM/Chroma, LangGraph, JWT, both React
portals and existing request/status model. Add request origin and durable JSON
workflow snapshot with migration; derive ordered pre-booking features; normalize
PDF text and validate actual policy permission; implement automatic authorized
medium-risk benefit and persisted manager paths. Complete customer state links
and offer response. Harden environment configuration and supply Render blueprint
and explicit limitations. Verify clean/existing PostgreSQL, Docker, tests and UI.
