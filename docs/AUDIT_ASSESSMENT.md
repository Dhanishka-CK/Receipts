# Receipts: Comprehensive Repository Audit & Architectural Assessment

**Project:** Receipts  
**Hackathon:** The Dawn of the Autonomous AI Builder (AI House × HiDevs)  
**Mandatory Stack:** Omi (Voice Input/Webhook) × Qdrant (Vector Memory) × Lyzr (Multi-Agent Reasoning)  
**Date:** October 8, 2026  

---

## 1. Executive Summary

The existing repository has a solid, well-scoped foundation:
- A clean 3-agent conceptual model (**Extractor** → **Auditor** → **Manager**).
- FastAPI backend with initial endpoints for Omi webhooks, ingest, and polling.
- Qdrant vector memory integration with payload filtering.
- In-memory event trace and alert logging.
- Minimal prototype UI.

However, several critical bugs, architectural gaps, and hackathon compliance risks prevent it from functioning as a winning autonomous product:
1. **Testing Failure**: `pytest` fails immediately with `ModuleNotFoundError: No module named 'receipts'`.
2. **Omi Webhook Fragility**: Strict query parameter requirements (`?uid=...`) cause 422 Unprocessable Entity on standard Omi webhooks. Missing flexible payload normalizer for varied Omi webhook schemas (transcripts, conversations, audio chunks).
3. **Auditor / Blocker Reasoning Gaps**: The mock auditor lacks support for blocker-dependency chains ("auth API blocks demo" → commitment `BLOCKED`, "auth is fixed" → blocker resolved, "ship demo" → contradiction/readiness audit).
4. **Missing Endpoints Required by Brief**: `POST /ask` does not exist; endpoints for `/commitments`, `/decisions`, `/status` are missing.
5. **No Pydantic Validation Models**: Endpoints accept unstructured `dict` or `Any`, exposing the API to runtime parsing crashes.
6. **No CORS Middleware**: Frontend calls fail when hosted across origins or during local dev on different ports.
7. **Frontend is a Developer Dashboard**: Lacks the core "Receipt" metaphor, live autonomous pipeline visualization, dedicated views for commitments, decisions, evidence inspection, and 1-click judge demo walkthrough.
8. **Qdrant Resilience**: Health check does not verify Qdrant connection; failure degrades abruptly rather than gracefully.
