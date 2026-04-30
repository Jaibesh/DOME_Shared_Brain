# 01 — System Architecture

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CLOUD HOST (GCP / Railway)                    │
│                                                                  │
│  ┌──────────────┐    ┌──────────────────┐    ┌───────────────┐  │
│  │  React SPA   │───▶│  FastAPI Backend  │───▶│  AI Agent     │  │
│  │  (Frontend)  │◀───│  (API Gateway)    │◀───│  Orchestrator │  │
│  └──────────────┘    └────────┬─────────┘    └───────┬───────┘  │
│                               │                       │          │
│                    ┌──────────┴──────────┐            │          │
│                    │                     │            │          │
│              ┌─────▼─────┐    ┌─────────▼──┐  ┌─────▼───────┐  │
│              │ Supabase   │    │ Vector DB  │  │ Knowledge   │  │
│              │ PostgreSQL │    │ (pgvector) │  │ Graph       │  │
│              │            │    │            │  │ (Neo4j/pg)  │  │
│              └────────────┘    └────────────┘  └─────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Document Store (Cloud Storage)               │   │
│  │  Service Manuals │ Parts Catalogs │ Schematics │ TSBs    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         Polaris Portal Agent (Playwright Automation)      │   │
│  │  Parts Lookup │ Price Check │ Order Submission             │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Technology Stack

### Why This Stack (Alignment with DOME Ecosystem)

The stack is chosen to **maximize reuse** of existing DOME infrastructure while adding the AI/ML capabilities this project requires.

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Frontend** | React + Vite | Same as Operations Dashboard — team already proficient |
| **Backend API** | FastAPI (Python) | Same as all DOME agents — async, fast, typed |
| **Database** | Supabase (PostgreSQL) | Already in production for reservations, waivers, etc. |
| **Vector Store** | Supabase pgvector | Native PostgreSQL extension — no separate vector DB needed |
| **LLM Provider** | Google Gemini 2.5 Pro | Multimodal (vision + text), long context (1M tokens), cost-effective |
| **Embeddings** | Gemini text-embedding-004 | 768 dimensions, optimized for retrieval |
| **Document Processing** | PDF → Markdown + VLM | Structure-aware parsing preserving tables, diagrams |
| **Browser Automation** | Playwright (Python) | Proven pattern across all DOME agents (MPOWR, TripWorks) |
| **Knowledge Graph** | Apache AGE (PostgreSQL) | Graph extension for PostgreSQL — stays in Supabase ecosystem |
| **Cloud Host** | Google Cloud Run | Containerized, auto-scaling, pay-per-use |
| **File Storage** | Google Cloud Storage | PDFs, schematics, processed documents |
| **Auth** | Supabase Auth | Built-in, already available in our Supabase instance |
| **Notifications** | Slack (existing) | Reuse `slack_notifier.py` from shared modules |

---

## Data Flow — Damage Report to Parts Order

```
MECHANIC                    SYSTEM                         EXTERNAL
────────                    ──────                         ────────
                                                           
1. Select Vehicle ─────▶ Load vehicle profile             
                         (VIN, model, year, mileage)       
                                                           
2. Describe Damage ────▶ AI Agent receives message         
                         │                                 
                         ├─▶ Query Vector DB               
                         │   (service manual chunks)       
                         │                                 
                         ├─▶ Query Knowledge Graph         
                         │   (part relationships)          
                         │                                 
                         ├─▶ Retrieve schematics           
                         │   (exploded diagrams)           
                         │                                 
                         └─▶ Generate Response:            
                             • Repair procedure            
                             • Parts list                  
                             • Schematics                  
                                                           
3. Review Parts List ──▶ Editable document UI              
   (add/remove/edit)                                       
                                                           
4. Approve Order ──────▶ Parts Order Agent ───────────▶ Polaris Dealer
                         (Playwright automation)        Portal
                         │                              (polarisdealers.com)
                         └─▶ Order confirmation ──────▶ Supabase (log)
                                                       + Slack alert
```

---

## Module Breakdown

### 1. Frontend (`/frontend`)
- React SPA with Vite
- Vehicle selector component
- Chat interface (streaming responses)
- Parts list editor (table with add/remove/quantity)
- Schematic viewer (zoomable image viewer)
- Order history dashboard

### 2. API Gateway (`/api`)
- FastAPI application
- Endpoints: `/vehicles`, `/chat`, `/parts`, `/orders`, `/schematics`
- WebSocket support for streaming chat responses
- Authentication middleware (Supabase JWT)
- Rate limiting and request validation

### 3. AI Agent Core (`/agent`)
- LLM orchestration (Gemini 2.5 Pro)
- RAG pipeline (retrieve → re-rank → generate)
- Tool calling for parts lookup, schematic retrieval
- Conversation memory (per-session context)
- Agentic routing (simple vs. complex queries)

### 4. Knowledge Engine (`/knowledge`)
- Document ingestion pipeline
- PDF → Markdown converter
- Vision model schematic analyzer
- Vector embedding generator
- Knowledge graph builder
- Hybrid search (semantic + keyword)

### 5. Polaris Portal Agent (`/portal_agent`)
- Playwright-based browser automation
- Parts lookup automation
- Price verification
- Order submission
- Session management and retry logic

### 6. Shared Infrastructure (`/shared`)
- Extend existing DOME shared modules
- Supabase helpers, Slack notifier, bot logger
- Common types and data models

---

## Database Schema (Supabase)

### Core Tables

```sql
-- Fleet vehicles with VIN-level detail
CREATE TABLE vehicles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    unit_id TEXT UNIQUE NOT NULL,        -- e.g., "RZR-01"
    vin TEXT UNIQUE NOT NULL,
    model TEXT NOT NULL,                  -- e.g., "RZR XP 1000"
    model_year INTEGER NOT NULL,
    trim TEXT,
    engine TEXT,
    current_miles INTEGER,
    status TEXT DEFAULT 'active',
    mpowr_vehicle_id TEXT,               -- link to MPOWR
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Repair sessions (one per damage report)
CREATE TABLE repair_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id UUID REFERENCES vehicles(id),
    mechanic_name TEXT NOT NULL,
    damage_description TEXT NOT NULL,
    ai_diagnosis TEXT,
    repair_procedure TEXT,
    status TEXT DEFAULT 'draft',         -- draft, parts_ordered, in_progress, completed
    created_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- Parts list for each repair session
CREATE TABLE repair_parts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES repair_sessions(id),
    part_number TEXT NOT NULL,
    part_name TEXT NOT NULL,
    quantity INTEGER DEFAULT 1,
    unit_price DECIMAL(10,2),
    category TEXT,                        -- e.g., "Suspension", "Drivetrain"
    source TEXT DEFAULT 'ai_suggested',   -- ai_suggested, manual_add
    is_approved BOOLEAN DEFAULT false,
    notes TEXT
);

-- Order tracking
CREATE TABLE parts_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES repair_sessions(id),
    polaris_order_id TEXT,
    order_status TEXT DEFAULT 'pending',  -- pending, submitted, confirmed, shipped
    total_cost DECIMAL(10,2),
    submitted_at TIMESTAMPTZ,
    submitted_by TEXT
);

-- Vector embeddings for RAG
CREATE TABLE document_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    metadata JSONB NOT NULL,             -- {source, page, section, vehicle_model, year}
    embedding VECTOR(768),               -- Gemini embedding dimension
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Create HNSW index for fast vector search
CREATE INDEX ON document_embeddings 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

---

*Continue to → [02_KNOWLEDGE_ENGINE.md](./02_KNOWLEDGE_ENGINE.md)*
