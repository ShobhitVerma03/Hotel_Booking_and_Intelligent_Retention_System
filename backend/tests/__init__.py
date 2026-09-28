"""Backend test package."""
"""Test bootstrap for the isolated FastAPI backend suite."""

import os

# This is intentionally test-only. It is set before individual test modules
# import cached application settings, while production still requires a secret.
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-with-at-least-thirty-two-characters")
