"""Black-box Docker CI smoke coverage for the complete hotel platform.

Uses synthetic CI data and never prints tokens, passwords, or policy text.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BACKEND = f"http://127.0.0.1:{os.environ['BACKEND_PORT']}/api/v1"
CUSTOMER = f"http://127.0.0.1:{os.environ['CUSTOMER_FRONTEND_PORT']}/api/v1"
MANAGER = f"http://127.0.0.1:{os.environ['MANAGER_FRONTEND_PORT']}/api/v1"
RUN_ID = os.environ.get("BUILD_TAG", str(int(time.time()))).replace(" ", "-").replace("/", "-")


def call(base: str, path: str, method: str = "GET", payload: dict | None = None, token: str | None = None) -> tuple[int, dict | list | str]:
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    try:
        with urlopen(Request(f"{base}{path}", data=data, headers=headers, method=method), timeout=30) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def expect(actual: int, expected: int, label: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{label}: expected HTTP {expected}, received {actual}")


def post(base: str, path: str, payload: dict, token: str | None = None) -> tuple[int, dict | list | str]:
    return call(base, path, "POST", payload, token)


def manager_login() -> str:
    status, body = post(MANAGER, "/auth/login", {"email": os.environ["DEV_MANAGER_EMAIL"], "password": os.environ["DEV_MANAGER_PASSWORD"]})
    expect(status, 200, "manager login")
    assert isinstance(body, dict)
    return body["access_token"]


def customer_case(action: str, index: int, manager_token: str) -> None:
    email = f"ci.customer.{RUN_ID}.{index}@hotel-example.com".lower()
    status, customer = post(CUSTOMER, "/auth/register", {"name": f"CI Customer {index}", "email": email, "phone": f"9000000{index:03d}", "password": "CiSmokePass123!"})
    expect(status, 201, "customer registration")
    assert isinstance(customer, dict)
    customer_token, customer_id = customer["access_token"], customer["user"]["customer_id"]
    status, login = post(CUSTOMER, "/auth/login", {"email": email, "password": "CiSmokePass123!"})
    expect(status, 200, "customer login")
    assert isinstance(login, dict) and login["access_token"]

    status, rooms = call(CUSTOMER, "/rooms")
    expect(status, 200, "room listing")
    assert isinstance(rooms, list) and rooms
    room_id = rooms[0]["room_id"]
    start = date(2035, 1, 1) + timedelta(days=index * 14)
    bookings: list[dict] = []
    for position in range(3):
        check_in = start + timedelta(days=position * 3)
        status, booking = post(CUSTOMER, "/bookings", {"customer_id": customer_id, "room_id": room_id, "check_in": check_in.isoformat(), "check_out": (check_in + timedelta(days=2)).isoformat(), "guests": 1}, customer_token)
        expect(status, 201, "booking creation")
        assert isinstance(booking, dict)
        bookings.append(booking)

    status, retention = post(CUSTOMER, f"/bookings/{bookings[-1]['booking_id']}/cancellation-request", {"reason": f"CI verification: {action}"}, customer_token)
    expect(status, 201, "cancellation request")
    assert isinstance(retention, dict)
    request_id = retention["request_id"]
    status, recommendation = post(MANAGER, f"/admin/retention-requests/{request_id}/recommendation", {}, manager_token)
    expect(status, 200, "retention recommendation")
    assert isinstance(recommendation, dict)
    if recommendation.get("workflow_status") != "AWAITING_MANAGER":
        raise RuntimeError("workflow did not reach AWAITING_MANAGER")
    offer = recommendation.get("recommendation") or {}
    if not offer.get("offer_type"):
        raise RuntimeError("recommendation has no manager-decision-ready offer")

    decision: dict = {"action": action, "comment": f"CI verification: {action}"}
    if action == "modify":
        modified = {"offer_type": offer["offer_type"], "description": "Manager-customized CI verification offer"}
        if offer.get("discount_percentage") is not None:
            modified["discount_percentage"] = min(float(offer["discount_percentage"]), 10.0)
        decision["modified_offer"] = modified
    status, result = post(MANAGER, f"/admin/retention-requests/{request_id}/decision", decision, manager_token)
    expect(status, 200, f"manager {action} decision")
    assert isinstance(result, dict)

    status, customer_offer = call(CUSTOMER, f"/bookings/retention-requests/{request_id}", token=customer_token)
    expect(status, 200, "customer offer view")
    assert isinstance(customer_offer, dict)
    if customer_offer.get("booking_status") != "cancel_pending":
        raise RuntimeError("manager decision incorrectly changed booking status")
    has_offer = customer_offer.get("offer") is not None
    if action in {"approve", "modify"} and not has_offer:
        raise RuntimeError(f"{action} did not publish a customer offer")
    if action == "reject" and has_offer:
        raise RuntimeError("reject unexpectedly published a customer offer")


def main() -> None:
    status, _ = call(BACKEND, "/health")
    expect(status, 200, "backend health")
    status, _ = call(MANAGER, "/admin/dashboard")
    expect(status, 401, "unauthenticated manager route")
    token = manager_login()
    status, _ = call(MANAGER, "/admin/dashboard", token=token)
    expect(status, 200, "manager dashboard")
    for index, action in enumerate(("approve", "modify", "reject"), start=1):
        customer_case(action, index, token)

    status, rag = post(MANAGER, "/admin/rag/policy-search", {"query": "What retention policy applies to a high-risk customer?"}, token)
    expect(status, 200, "RAG policy search")
    assert isinstance(rag, dict) and rag.get("results")
    first = rag["results"][0]
    if not all(first.get(key) for key in ("source", "page", "chunk_id")):
        raise RuntimeError("RAG result lacks source traceability metadata")
    status, analytics = post(MANAGER, "/admin/nl-sql/query", {"question": "How many bookings are there?"}, token)
    expect(status, 200, "safe NL-to-SQL analytics")
    assert isinstance(analytics, dict) and analytics.get("row_count") is not None
    print("Docker integration smoke test passed.")


if __name__ == "__main__":
    main()
