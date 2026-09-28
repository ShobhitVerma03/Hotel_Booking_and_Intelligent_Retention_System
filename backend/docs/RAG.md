# Phase 7: Hotel-policy retrieval (RAG)

The confidential `data/policy/Company_Retention_Policy_2026.pdf` remains a server-side file. It is never served by the API and clients cannot choose a document path, Chroma directory, or collection.

`PolicyIngestionService` uses `pypdf` to extract each page, splits each page with configurable character chunks and overlap, embeds each chunk using the local `all-MiniLM-L6-v2` SentenceTransformer model, and upserts it into the configured persistent Chroma collection. Chunk IDs are deterministic (`company-retention-policy-2026-p{page}-c{chunk}`), so repeated ingestion updates existing records instead of deleting or duplicating the collection.

Each record contains document name, page, chunk index, and chunk ID. `PolicyRAGService.retrieve_policy(query, top_k)` embeds a query and returns policy text with this provenance. It is reusable by a future workflow but makes no business decision.

The manager-only inspection endpoint is `POST /api/v1/admin/rag/policy-search` with `{ "query": "...", "top_k": 3 }`. It returns context and provenance only; it cannot create offers, alter bookings, change retention requests, or create decisions.

Relevant configuration is in `.env.example`: `RAG_ENABLED`, `RAG_COLLECTION_NAME`, `RAG_PERSIST_DIRECTORY`, `RAG_EMBEDDING_MODEL`, `RAG_TOP_K`, `RAG_CHUNK_SIZE`, `RAG_CHUNK_OVERLAP`, and `RAG_POLICY_DOCUMENT_PATH`. To safely rebuild/update the configured index, call `PolicyIngestionService().ingest_policy()`; it uses upsert and never removes the store.

System boundaries: ML predicts cancellation risk; RAG retrieves policy context; LangGraph will orchestrate a later workflow; HITL will be a later manager decision. RAG itself does not calculate discounts or produce a policy answer.
