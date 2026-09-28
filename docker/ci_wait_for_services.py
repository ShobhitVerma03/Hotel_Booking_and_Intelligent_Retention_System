"""Poll Compose HTTP endpoints instead of using arbitrary startup sleeps."""
from __future__ import annotations

import os
import time
from urllib.error import URLError
from urllib.request import urlopen


def is_ready(url: str) -> bool:
    try:
        with urlopen(url, timeout=3) as response:
            return response.status == 200
    except (URLError, TimeoutError):
        return False


urls = (
    f"http://127.0.0.1:{os.environ['BACKEND_PORT']}/api/v1/health",
    f"http://127.0.0.1:{os.environ['CUSTOMER_FRONTEND_PORT']}/",
    f"http://127.0.0.1:{os.environ['MANAGER_FRONTEND_PORT']}/",
)
deadline = time.monotonic() + 180
while time.monotonic() < deadline:
    if all(is_ready(url) for url in urls):
        print("Backend and frontend endpoints are ready.")
        raise SystemExit(0)
    time.sleep(2)
raise SystemExit("Timed out waiting for the Docker stack to become ready")
