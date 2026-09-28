# Phase 8: Retention recommendation workflow

The production backend uses an explicit LangGraph state graph, not the legacy Flask ReAct chat loop. It executes: `load_context` -> `evaluate_risk` -> `retrieve_policy` -> `generate_recommendation` -> `AWAITING_MANAGER`.

`RetentionWorkflowService` checkpoints state in the configured SQLite database using the retention request ID as its stable thread identifier. Repeating the request after it reaches `AWAITING_MANAGER` reads the saved state instead of generating a second recommendation/audit event. The checkpoint holds workflow context only; it is not the business database.

The graph uses the existing ML prediction and `PolicyRAGService`. It does not call an LLM in Phase 8. Recommendations are deterministic, structured, policy-grounded, and require manager review. A current-booking rate discount is only proposed when a numerical limit can be parsed from retrieved policy context; otherwise the result requires policy review and contains no discount.

The manager-only endpoint is `POST /api/v1/admin/retention-requests/{request_id}/recommendation`. It does not create an offer, change booking/request status, approve/reject anything, or contact the customer. Phase 9 will add manager HITL decisions.

Boundaries: ML predicts risk; RAG retrieves policy; LangGraph orchestrates a recommendation; a future manager provides the decision; a future customer accepts or rejects the final offer.
