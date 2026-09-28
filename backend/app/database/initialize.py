"""Container-safe, idempotent reference-data initialization after Alembic."""

from backend.app.database.seed import seed_database
from backend.app.database.session import SessionLocal


def main() -> None:
    with SessionLocal() as db:
        seed_database(db)


if __name__ == "__main__":
    main()
