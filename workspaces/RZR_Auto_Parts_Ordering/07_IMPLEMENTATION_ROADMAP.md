# 07 — Implementation Roadmap

## Phased Development Plan

This project is broken into **4 phases** over approximately **10-14 weeks** of active development. Each phase delivers usable functionality that can be tested and validated before moving on.

---

## Phase 0: Foundation (Week 1-2)
**Goal:** Acquire documents, set up infrastructure, prove the concept works.

### Tasks
- [ ] **Acquire service manuals** — Purchase official PDF service manuals for every model/year in the fleet (~$30-50 each)
- [ ] **Download owner's manuals** — Free from Polaris website
- [ ] **Export parts catalogs** — Screenshot/export all assembly categories from polaris.com for each VIN
- [ ] **Set up project structure** — Create workspace under `DOME_CORE/workspaces/RZR_Auto_Parts_Ordering/`
- [ ] **Set up Supabase tables** — Create `vehicles`, `parts_catalog`, `document_embeddings`, `repair_sessions`, `repair_parts`, `parts_orders` tables
- [ ] **Enable pgvector** — Enable the vector extension on Supabase, create HNSW index
- [ ] **GCP project setup** — Create project, enable Cloud Run, Cloud Storage, Secret Manager
- [ ] **Proof of concept** — Process ONE service manual chapter through the pipeline:
  - PDF → Markdown extraction
  - Schematic analysis with Gemini Vision
  - Embed and store in pgvector
  - Query and retrieve with a test question

### Deliverable
A Jupyter notebook demonstrating: "Given a service manual PDF page about CV axle replacement, can our pipeline extract it, embed it, and accurately retrieve it when asked 'How do I replace a front CV axle on a 2024 RZR XP 1000?'"

---

## Phase 1: Knowledge Engine (Week 3-5)
**Goal:** Ingest ALL documentation and build the complete knowledge base.

### Tasks
- [ ] **Build ingestion pipeline** (`knowledge/ingest.py`)
  - PDF → Markdown converter (PyMuPDF + Docling)
  - Image extraction for schematics
  - VLM analysis of every schematic page (Gemini Vision)
  - Intelligent chunking (parent-child, section-aware)
  - Metadata tagging (model, year, section, content type)
  - Batch embedding generation (Gemini text-embedding-004)
- [ ] **Ingest all service manuals** — Process every manual for every fleet vehicle
- [ ] **Build parts catalog database** — Playwright scraper for polaris.com parts catalog
  - Export every assembly category for every VIN
  - Store in `parts_catalog` table with full metadata
- [ ] **Build knowledge graph** — Map part relationships
  - Vehicle → System → Component → Part Number relationships
  - "Commonly replaced together" associations
  - Tool requirements per repair
  - Torque specs and fluid specifications
- [ ] **Build hybrid search** — Implement vector + BM25 + re-ranking pipeline
- [ ] **Evaluation framework** — Create test queries with known-good answers
  - Retrieval accuracy (Recall@K, MRR)
  - At least 30 test queries covering common repairs

### Deliverable
A search API endpoint that, given a natural language repair question and vehicle ID, returns the correct service manual sections, part numbers, and schematics with >90% retrieval accuracy.

---

## Phase 2: AI Agent + Frontend (Week 6-9)
**Goal:** Build the conversational AI and the mechanic-facing web application.

### Tasks
- [ ] **AI Agent Core** (`agent/`)
  - Gemini 2.5 Pro integration with tool calling
  - System prompt with mechanic-focused persona
  - Tool implementations (search manual, lookup parts, get schematic, etc.)
  - Conversation memory management
  - Part number validation post-processing
  - Confidence scoring and clarification logic
- [ ] **FastAPI Backend** (`api/`)
  - REST endpoints for vehicles, parts, orders, schematics
  - WebSocket endpoint for streaming chat responses
  - Supabase Auth middleware
  - Request validation and error handling
- [ ] **React Frontend** (`frontend/`)
  - Vehicle selector sidebar
  - Chat interface with streaming responses
  - Markdown rendering for procedures, tables, warnings
  - Inline schematic thumbnails
  - Parts panel (editable table with add/remove/quantity)
  - Schematic viewer (zoom/pan)
  - Order summary and PDF export
  - Responsive layout for laptop screens
- [ ] **Integration testing** — End-to-end flow:
  - Select vehicle → Describe damage → Get diagnosis → Review parts → Export list

### Deliverable
A locally-running web app where a mechanic can chat with the AI about vehicle damage and receive accurate repair procedures and parts lists. PDF export for manual ordering.

---

## Phase 3: Cloud Deployment + Portal Automation (Week 10-12)
**Goal:** Deploy to cloud, add Polaris portal ordering automation.

### Tasks
- [ ] **Dockerize application** — Single container with FastAPI + React + Playwright
- [ ] **Deploy to Cloud Run** — Auto-scaling, custom domain
- [ ] **Set up CI/CD** — GitHub Actions → build → test → deploy
- [ ] **Polaris portal agent** (if dealer credentials available)
  - Login automation for polarisdealers.com
  - Parts search and cart building
  - Order submission
  - Confirmation capture
  - Error handling and retry logic
- [ ] **Order tracking system** — Supabase tables for order lifecycle
- [ ] **Slack notifications** — Order submitted, order confirmed, errors
- [ ] **User authentication** — Supabase Auth with mechanic accounts
- [ ] **Security hardening** — RLS policies, secret management, HTTPS

### Deliverable
A cloud-hosted application accessible from any laptop, with optional automated parts ordering through the Polaris dealer portal.

---

## Phase 4: Polish & Advanced Features (Week 13-14+)
**Goal:** Refine based on mechanic feedback, add advanced capabilities.

### Tasks
- [ ] **Mechanic feedback integration** — Iterate on UI/UX based on real shop usage
- [ ] **Repair history tracking** — Log all repairs per vehicle, surface trends
- [ ] **MPOWR integration** — Link repair sessions to MPOWR work orders
- [ ] **Predictive maintenance** — Analyze repair history + mileage to suggest upcoming needs
- [ ] **Parts inventory tracking** — Track parts in stock vs. needs ordering
- [ ] **Cost reporting** — Per-vehicle repair costs, fleet-wide analytics
- [ ] **Offline mode** (stretch) — PWA with cached data for areas with poor connectivity

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Service manual quality varies by year | Medium | High | Test extraction on manuals from each year before bulk processing |
| Polaris changes their website structure | Medium | Medium | Same issue we handle with MPOWR — resilient selectors + monitoring |
| AI hallucinates part numbers | High (if unmitigated) | Critical | Constrained to catalog DB only — never generate part numbers |
| Mechanic adoption resistance | Medium | High | Involve mechanics early, iterate on UX based on their feedback |
| Gemini API costs exceed budget | Low | Medium | Implement caching for repeated queries, use smaller models for simple tasks |
| No Polaris dealer credentials available | Medium | Medium | Tier 1 strategy (PDF export) works without credentials |

---

## Prerequisites & Decision Points

Before development begins, we need decisions on:

1. **Service manuals** — Do we purchase official PDFs, or are they already available?
2. **Polaris dealer credentials** — Does Epic 4x4 have a dealer account on polarisdealers.com? This determines whether we can automate ordering (Tier 2) or just generate parts lists (Tier 1).
3. **Fleet vehicle list** — Need exact VINs for every vehicle to build VIN-specific parts catalogs.
4. **GCP vs. existing cloud** — Confirm GCP is the right cloud provider (best Gemini integration) or if we should use another platform.
5. **Budget** — Estimated ~$300-500 one-time (manuals) + ~$75-120/mo operating costs. Acceptable?

---

## Summary

This project is absolutely achievable with our existing tech stack and proven patterns. The architecture mirrors what we've already built for MPOWR (Playwright automation, Supabase, FastAPI, Slack notifications) — we're adding an AI/RAG layer on top.

The **hardest part** is Phase 1 (Knowledge Engine) — getting high-quality, searchable data out of PDF service manuals. Everything after that is application development that plays to our strengths.

**Start with Phase 0's proof-of-concept** to validate the approach before committing to the full build.
