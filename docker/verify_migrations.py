"""Validate clean and existing-schema upgrades on a disposable PostgreSQL DB."""
import os
import subprocess
import uuid
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import make_url
from backend.app.core.config import get_settings

url = make_url(get_settings().database_url)
assert url.drivername.startswith("postgresql")
name = "hotel_migration_test_" + uuid.uuid4().hex[:12]
admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
with admin.connect() as connection:
    connection.execute(text(f'CREATE DATABASE "{name}"'))
test_url = url.set(database=name)
env = {**os.environ, "DATABASE_URL":test_url.render_as_string(hide_password=False)}
engine = create_engine(test_url)
try:
    command = ["python", "-m", "alembic", "-c", "/app/backend/alembic.ini"]
    subprocess.run(command + ["upgrade", "head"], env=env, check=True)
    with engine.begin() as db:
        assert db.execute(text("SELECT version_num FROM alembic_version")).scalar() == "20260929_0003"
        db.execute(text("INSERT INTO users (email, role, is_active) VALUES ('migration-check@example.com', 'CUSTOMER', true)"))
    # Recreate the immediately preceding schema, then upgrade with existing data.
    subprocess.run(command + ["downgrade", "20260928_0002"], env=env, check=True)
    assert "workflow_state" not in {c["name"] for c in inspect(engine).get_columns("retention_requests")}
    subprocess.run(command + ["upgrade", "head"], env=env, check=True)
    with engine.connect() as db:
        assert db.execute(text("SELECT count(*) FROM users WHERE email='migration-check@example.com'")).scalar() == 1
    print("PASS: clean PostgreSQL migration and existing-schema upgrade preserve data")
finally:
    engine.dispose()
    # Only this uniquely named database created by this process is removed.
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE "{name}"'))
    admin.dispose()
