"""Real HTTP/PostgreSQL/ML/RAG verification; never prints credentials or tokens.

Run inside the backend container via stdin or copy this script into /tmp.
The test creates explicitly named synthetic guests/bookings through public APIs.
"""
import os
import secrets
import uuid
from datetime import date, timedelta
import httpx

base = os.getenv("VERIFY_API_URL", "http://127.0.0.1:8000/api/v1")
client = httpx.Client(base_url=base, timeout=120)


def call(method, path, token=None, expected=200, **kwargs):
    headers = {"Authorization": "Bearer " + token} if token else {}
    response = client.request(method, path, headers=headers, **kwargs)
    assert response.status_code == expected, (method, path, response.status_code, response.text)
    return response.json()


manager = call("POST", "/auth/login", json={"email":os.environ["DEV_MANAGER_EMAIL"], "password":os.environ["DEV_MANAGER_PASSWORD"]})["access_token"]
run_id = uuid.uuid4().hex[:12]
password = secrets.token_urlsafe(24)
guest = call("POST", "/auth/register", expected=201, json={"name":"E2E verification " + run_id, "email":f"verify-{run_id}@example.com", "password":password})
token, cid = guest["access_token"], guest["user"]["customer_id"]
call("POST", "/auth/login", expected=401, json={"email":guest["user"]["email"], "password": "invalid-" + password})
call("POST", "/auth/login", json={"email":guest["user"]["email"], "password":password})
call("GET", "/admin/dashboard", token, expected=403)
start = date(2028, 1, 1) + timedelta(days=secrets.randbelow(500))


def book(offset):
    for shift in range(60):
        arrival = start + timedelta(days=offset+shift)
        params = {"check_in":str(arrival), "check_out":str(arrival+timedelta(days=1))}
        rooms = call("GET", "/rooms/available", params=params)
        if rooms:
            return call("POST", "/bookings", token, expected=201, json={**params,"room_id":rooms[0]["room_id"],"customer_id":cid,"guests":1})
    raise AssertionError("No available test dates")


first = book(0)
assert first["welcome_offer"] and not first["retention_requests"]
rid = call("POST", f"/bookings/{first['booking_id']}/cancellation-request", token, expected=201, json={"reason":"E2E cancellation approval"})["request_id"]
call("POST", f"/admin/cancellation-requests/{rid}/resolution", token, expected=403, json={"action":"approve_cancellation"})
pending = call("GET", "/admin/cancellation-requests", manager, params={"booking_id":first["booking_id"]})
assert pending["items"][0]["status"] == "pending"
call("POST", f"/admin/cancellation-requests/{rid}/resolution", manager, json={"action":"approve_cancellation"})
assert call("GET", f"/bookings/{first['booking_id']}", token)["status"] == "cancelled"

second = book(4)
rid = second["retention_requests"][0]["request_id"]
workflow = call("GET", f"/admin/retention-requests/{rid}", manager)["workflow"]
assert workflow and workflow["risk_score"] is not None
assert workflow["policy_results"] and all(e["source"].endswith(".pdf") for e in workflow["policy_results"])
if workflow["workflow_status"] == "AWAITING_MANAGER":
    call("POST", f"/admin/retention-requests/{rid}/decision", manager, json={"action":"approve"})
else:
    assert workflow["workflow_status"] == "AUTO_OFFERED"
assert call("GET", f"/bookings/retention-requests/{rid}", token)["offer"]
assert call("POST", f"/bookings/retention-requests/{rid}/response", token, json={"action":"accept"})["status"] == "accepted"

rid = call("POST", f"/bookings/{second['booking_id']}/cancellation-request", token, expected=201, json={"reason":"E2E cancellation rejection"})["request_id"]
call("POST", f"/admin/cancellation-requests/{rid}/resolution", manager, json={"action":"decline_cancellation"})
assert call("GET", f"/bookings/{second['booking_id']}", token)["status"] == "confirmed"
assert "rejected" in call("GET", f"/bookings/retention-requests/{rid}", token)["message"]
assert len(call("GET", f"/customers/{cid}/bookings", token)) == 2

third = book(8)
rid = third["retention_requests"][0]["request_id"]
workflow3 = call("GET", f"/admin/retention-requests/{rid}", manager)["workflow"]
if workflow3["workflow_status"] == "AWAITING_MANAGER":
    call("POST", f"/admin/retention-requests/{rid}/decision", manager, json={"action":"reject"})
else:
    call("POST", f"/bookings/retention-requests/{rid}/response", token, json={"action":"reject"})
assert call("GET", f"/bookings/retention-requests/{rid}", token)["status"] == "rejected"
assert call("GET", "/health")["status"] == "healthy"
print(f"PASS: real HTTP E2E guest={cid}; cancellation approve/reject; second booking risk={workflow['risk_category']}; policy evidence; {workflow['workflow_status']}; offer acceptance; third offer rejection.")
