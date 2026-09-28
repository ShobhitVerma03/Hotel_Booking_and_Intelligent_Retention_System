# Aurora Stay React portals

`customer/` and `manager/` are separate Vite React applications. Both use the
existing FastAPI REST API through `VITE_API_BASE_URL` (default
`http://localhost:8000`) and never embed backend credentials.

Run each independently:

```bash
cd frontend/customer && npm install && npm run dev
cd frontend/manager && npm install && npm run dev
```

Each app also exposes `npm test` and `npm run build`. Customer routes include
login, registration, rooms, booking, booking history/details, and finalized
retention-offer status. Manager routes include dashboard, customers, bookings,
cancellations, retention/HITL, analytics, and audit history.

The backend remains the authorization and business-rule authority. Customer
offer acceptance/rejection is intentionally not implemented in this phase.
