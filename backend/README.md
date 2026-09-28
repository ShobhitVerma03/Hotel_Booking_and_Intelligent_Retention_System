# FastAPI Platform Foundation

This is the Phase 2 backend foundation. It intentionally excludes authentication, AI/ML, RAG, LangGraph, customer cancellation handling, frontends, and deployment.

## Run locally

```powershell
pip install -r requirements.txt
alembic -c backend/alembic.ini upgrade head
uvicorn backend.app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`, with OpenAPI documentation at `/docs`.

## Database URLs

Local development defaults to `sqlite:///./data/hotel_platform.db`. Set `DATABASE_URL` to a PostgreSQL SQLAlchemy URL for production, for example `postgresql+psycopg://user:password@host:5432/hotel_platform`.

## Tests

```powershell
python -m unittest discover -s backend/tests -v
```
