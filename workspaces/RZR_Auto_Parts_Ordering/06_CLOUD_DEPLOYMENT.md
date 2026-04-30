# 06 — Local Development & Processing Infrastructure

## Local-First Architecture

To minimize Gemini API costs during development and document processing, the system will rely heavily on local processing. Heavy lifting such as PDF extraction, vector embedding, and LangGraph workflow orchestration will be run entirely on the local development machine.

```
┌─────────────────────────────────────────────────────────────────┐
│                     LOCAL MACHINE (Development)                 │
│                                                                  │
│  ┌──────────────┐    ┌──────────────────┐    ┌───────────────┐  │
│  │  React SPA   │───▶│  FastAPI Backend  │───▶│  LangGraph    │  │
│  │  (Frontend)  │◀───│  (API Gateway)    │◀───│  Agent        │  │
│  └──────────────┘    └────────┬─────────┘    └───────┬───────┘  │
│                               │                       │          │
│                    ┌──────────┴──────────┐            │          │
│                    │                     │            │          │
│              ┌─────▼─────┐    ┌─────────▼──┐  ┌─────▼───────┐  │
│              │ Local     │    │ Local DB   │  │ Local Graph │  │
│              │ PostgreSQL│    │ (pgvector) │  │ DB (Neo4j)  │  │
│              └────────────┘    └────────────┘  └─────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Local Document Processing Pipeline           │   │
│  │  Docling/PyMuPDF │ Local Embedding Models │ LangGraph     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Why Local First?

| Feature | Benefit |
|---------|---------|
| **Cost Savings** | Massive reduction in API costs. Parsing thousands of PDF pages locally is free. |
| **Data Privacy** | No proprietary Polaris manuals or sensitive fleet data uploaded to third-party APIs during the parsing stage. |
| **Rapid Iteration** | Instant feedback loop when tweaking extraction rules, LangGraph nodes, and database schemas. |
| **Complete Control** | Local containerized environment (Docker Compose) for PostgreSQL, pgvector, and frontend. |

### Local Stack Choices

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **LLM Orchestration** | LangGraph | State-based, cyclic graph workflows ideal for multi-step agent reasoning. |
| **Embedding Model** | Local Transformers (e.g. `nomic-embed-text` or `all-MiniLM-L6-v2`) | Completely free, fast local vector generation. |
| **Database** | Dockerized PostgreSQL with pgvector | Identical API to Supabase, but runs completely locally. |
| **Doc Parsing** | Docling / PyMuPDF | Local extraction of layout, tables, and images without API calls. |
| **LLM (Dev)** | Ollama (Llama 3 / Mistral) | Run local models for intermediate reasoning steps to save costs, saving Gemini only for complex final outputs if necessary. |

---

## Zero-Cost Ingestion Pipeline

The most expensive part of a RAG application is processing the initial knowledge base. By doing this locally:

1. **Extraction:** PyMuPDF extracts text, images, and layout from the `Vehicle_Documentation` folder.
2. **Vision Analysis:** Use a local vision model (e.g., LLaVA via Ollama) to analyze exploded schematics and extract part numbers without paying for Gemini Vision.
3. **Chunking & Embedding:** Use `sentence-transformers` locally to embed chunks into the local `pgvector` database.

---

## Deployment Strategy (Future)

Once the local processing is complete, the vector database is populated, and the application is stable:

1. The local PostgreSQL database dump can be pushed to the production Supabase instance.
2. The FastAPI backend and React frontend can be containerized and deployed to a low-cost VPS or Google Cloud Run.
3. The heavy document processing code is never deployed to the cloud, significantly reducing the cloud compute requirements.

---

*Continue to → [07_IMPLEMENTATION_ROADMAP.md](./07_IMPLEMENTATION_ROADMAP.md)*
