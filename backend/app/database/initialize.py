"""Container-safe, idempotent reference-data initialization after Alembic."""

from backend.app.database.seed import seed_database
from backend.app.database.session import SessionLocal
from backend.app.core.config import get_settings


def main() -> None:
    if not get_settings().seed_database:
        return
    with SessionLocal() as db:
        seed_database(db)


if __name__ == "__main__":
    main()
