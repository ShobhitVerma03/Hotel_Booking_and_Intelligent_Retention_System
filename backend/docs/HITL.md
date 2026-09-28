# Phase 9: Manager Human-in-the-Loop

Phase 8 produces a policy-grounded recommendation and pauses at
`AWAITING_MANAGER`. Phase 9 adds exactly one terminal manager decision through
`POST /api/v1/admin/retention-requests/{request_id}/decision`.

The manager-only request accepts `approve`, `modify`, or `reject` plus an
optional comment. `modify` is itself the final approval: it creates a final
customer-visible offer immediately; it does not require a second approval.

For approve and modify, the platform stores a `retention_decisions` record,
marks the retention request `offered`, and creates an `offers` record with
`available_to_customer` status. A modification must retain the policy-grounded
offer type and, where the Phase 8 recommendation has a numeric policy limit,
cannot exceed that limit. The original recommendation is retained in both the
decision payload and the retention request for audit comparison.

Reject records a manager decision and audit event but does not create an offer.
All paths preserve `bookings.status = cancel_pending`; Phase 9 never records a
customer response, cancels a booking, or finalizes a customer outcome.
