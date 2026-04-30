# 02 — Knowledge Engine (Document Ingestion & RAG Pipeline)

This is the **most critical component** of the entire system. The AI is only as good as the knowledge it can retrieve. This document details how we ingest, process, store, and retrieve technical documentation.

---

## Document Inventory — What We Need to Ingest

| Document Type | Source | Format | Est. Pages (per model) |
|--------------|--------|--------|----------------------|
| **Service Manual** | Polaris (purchase) or authorized digital resellers | PDF | 500-800 |
| **Parts Catalog** | Polaris dealer portal / polaris.com | PDF + Interactive Web | 200-400 |
| **Owner's Manual** | polaris.com (free download) | PDF | 100-150 |
| **Technical Service Bulletins (TSBs)** | Polaris dealer portal | PDF | 5-20 each |
| **Wiring Diagrams** | Inside service manual | PDF (visual) | 20-40 |
| **Exploded Assembly Diagrams** | Parts catalog | Images/PDF | 50-100 |

### Acquisition Strategy

1. **Service Manuals** — Purchase official factory service manuals for each model/year in the fleet. Digital PDFs available from Polaris directly or authorized resellers (Etsy, eBay for digital copies). **Budget ~$30-50 per manual**.
2. **Parts Catalogs** — Scrape/export from Polaris public parts catalog (polaris.com) using VIN lookup. Each assembly category has exploded diagrams with part numbers.
3. **Owner's Manuals** — Free from Polaris website Help Center.
4. **TSBs** — Available through Polaris dealer portal (requires dealer credentials).

> ⚠️ **IMPORTANT:** Always use VIN-specific lookups. Part numbers vary by model year, trim, and sometimes production date.

---

## Ingestion Pipeline Architecture

```
Raw Documents (PDF/Images)
         │
         ▼
┌─────────────────────────┐
│  Stage 1: Extraction     │
│  PDF → Structured Data   │
│  • Text extraction       │
│  • Table detection       │
│  • Image extraction      │
│  • Layout preservation   │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Stage 2: Enhancement    │
│  Visual Understanding    │
│  • Schematic analysis    │
│  • Diagram description   │
│  • Part number mapping   │
│  • Cross-referencing     │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Stage 3: Chunking       │
│  Intelligent Splitting   │
│  • Section-aware chunks  │
│  • Parent-child linking  │
│  • Metadata enrichment   │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Stage 4: Embedding      │
│  Vector + Graph Storage  │
│  • Semantic embeddings   │
│  • Keyword index (BM25)  │
│  • Knowledge graph nodes │
└─────────────────────────┘
```

---

## Stage 1: Document Extraction

### Text-Heavy Pages (Procedures, Specs)

Use **structure-aware PDF parsing** to convert to Markdown, preserving:
- Heading hierarchy (Chapter → Section → Subsection)
- Numbered/bulleted procedure steps
- Tables (torque specs, fluid capacities, part lists)
- Bold/italic formatting for warnings and notes

**Tools:**
- **PyMuPDF (fitz)** — Fast, reliable text + layout extraction
- **Docling** (by IBM) — State-of-the-art PDF → Markdown conversion with table detection
- **Fallback:** `pdfplumber` for complex table extraction

### Visual Pages (Schematics, Wiring Diagrams, Exploded Views)

Traditional OCR **will not work** for schematics. Use **Vision-Language Models (VLMs):**

1. Extract each page as a high-resolution image (300 DPI minimum)
2. Send to **Gemini 2.5 Pro (vision)** with a specialized prompt:

```python
SCHEMATIC_ANALYSIS_PROMPT = """
You are analyzing a Polaris service manual page. This is an exploded 
assembly diagram / schematic for a {vehicle_model} ({model_year}).

For this diagram, provide:

1. ASSEMBLY NAME: What system/assembly this diagram shows
2. COMPONENT LIST: Every labeled component with:
   - Reference number (from the diagram)
   - Part name
   - OEM Part number (if visible)
   - Quantity required
3. ASSEMBLY RELATIONSHIPS: How components connect/fit together
4. NOTES: Any torque specs, fluid types, or special instructions visible
5. RELATED SYSTEMS: What other assemblies/systems connect to this one

Output as structured JSON.
"""
```

3. Store both the raw image AND the structured text description
4. Link the image to the embedding for visual retrieval

---

## Stage 2: Parts Catalog Processing

The parts catalog requires special treatment because it's the **source of truth for part numbers**.

### Part Number Database Construction

```python
# Schema for the parts master table
CREATE TABLE parts_catalog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    part_number TEXT NOT NULL,
    part_name TEXT NOT NULL,
    superseded_by TEXT,                  -- newer part number if superseded
    vehicle_models TEXT[],               -- which models this fits
    model_years INTEGER[],              -- which years
    assembly_category TEXT,              -- "Engine", "Suspension", etc.
    assembly_subcategory TEXT,           -- "Front A-Arm", "CVT Belt", etc.
    diagram_reference TEXT,              -- reference # in exploded diagram
    diagram_image_url TEXT,              -- link to the diagram image
    msrp DECIMAL(10,2),
    weight_lbs DECIMAL(6,2),
    is_dealer_only BOOLEAN DEFAULT false,
    notes TEXT,
    last_verified TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Critical index for part number lookups
CREATE INDEX idx_parts_number ON parts_catalog(part_number);
CREATE INDEX idx_parts_model ON parts_catalog USING GIN(vehicle_models);
```

### Population Strategy

**Option A (Recommended): Playwright Scraper for Polaris Public Catalog**
- Navigate polaris.com → Parts → Shop by Vehicle
- Enter VIN for each fleet vehicle
- Iterate through every assembly category
- Extract all part numbers, names, and diagram images
- Store in `parts_catalog` table

**Option B: Manual PDF Processing**
- Process parts catalog PDFs through VLM pipeline
- Extract part numbers from exploded diagram legends
- Cross-reference with online catalog for pricing

**Option C: Dealer Portal Integration**
- If dealer credentials are available, scrape the richer dealer catalog
- Includes real-time pricing, availability, supersession data

---

## Stage 3: Intelligent Chunking

Standard fixed-size chunking destroys context in technical manuals. Use **hierarchical parent-child chunking:**

```
PARENT CHUNK (stored for LLM context):
├── Chapter: "Suspension System"
│   ├── Full section text (1000-2000 tokens)
│   └── References to child chunks
│
CHILD CHUNKS (stored for retrieval):
├── "Front A-Arm Removal - Step-by-step procedure" (200-400 tokens)
├── "Front A-Arm Torque Specifications - Table" (100-200 tokens)
├── "Front A-Arm Exploded Diagram - VLM description" (300-500 tokens)
└── "Front A-Arm Parts List - Part numbers" (100-300 tokens)
```

**How it works:**
1. Retrieve matching **child chunks** (granular, precise)
2. Expand to include the **parent chunk** for full context
3. Feed parent + children to the LLM for generation

### Metadata Enrichment

Every chunk gets tagged with:
```json
{
  "source": "2024_RZR_XP_1000_Service_Manual.pdf",
  "page_number": 245,
  "chapter": "Suspension System",
  "section": "Front A-Arm",
  "subsection": "Removal Procedure",
  "vehicle_model": "RZR XP 1000",
  "model_year": 2024,
  "content_type": "procedure",        // procedure, specification, diagram, parts_list, wiring
  "related_parts": ["2206026", "7042430", "7557803"],
  "parent_chunk_id": "uuid-xxx"
}
```

---

## Stage 4: Hybrid Retrieval Strategy

### Why Hybrid Search is Mandatory

| Search Type | Good For | Bad For |
|-------------|----------|---------|
| **Vector (Semantic)** | "How do I fix a clicking noise in the front end" | Finding exact part number "2206026" |
| **Keyword (BM25)** | Finding exact part number "2206026" | Understanding "clicking noise = CV joint" |

**We need both.**

### Retrieval Pipeline

```
User Query: "The front left CV axle is broken on RZR-07"
                    │
                    ▼
         ┌─────────────────┐
         │  Query Analyzer  │
         │  (classify type) │
         └────────┬────────┘
                  │
          ┌───────┴───────┐
          ▼               ▼
   ┌────────────┐  ┌────────────┐
   │  Vector    │  │  Keyword   │
   │  Search    │  │  Search    │
   │  (top 30)  │  │  (top 30)  │
   └─────┬──────┘  └─────┬──────┘
         │               │
         └───────┬───────┘
                 ▼
        ┌────────────────┐
        │  Re-Ranker      │
        │  (Cross-Encoder) │
        │  → top 8        │
        └────────┬───────┘
                 │
                 ▼
        ┌────────────────┐
        │  Context Builder │
        │  Expand parents  │
        │  Add schematics  │
        └────────┬───────┘
                 │
                 ▼
           Final Context
           → LLM Prompt
```

### Implementation

```python
async def hybrid_search(query: str, vehicle_id: str, top_k: int = 8):
    """Perform hybrid search combining semantic + keyword retrieval."""
    
    # 1. Generate query embedding
    query_embedding = await embed_text(query)
    
    # 2. Get vehicle metadata for filtering
    vehicle = await get_vehicle(vehicle_id)
    model_filter = vehicle.model
    year_filter = vehicle.model_year
    
    # 3. Vector search (semantic similarity)
    vector_results = await supabase.rpc('match_documents', {
        'query_embedding': query_embedding,
        'match_threshold': 0.7,
        'match_count': 30,
        'filter_model': model_filter,
        'filter_year': year_filter
    })
    
    # 4. Keyword search (BM25 via PostgreSQL full-text search)
    keyword_results = await supabase.rpc('keyword_search', {
        'query': query,
        'match_count': 30,
        'filter_model': model_filter,
        'filter_year': year_filter
    })
    
    # 5. Merge and deduplicate
    combined = merge_results(vector_results, keyword_results)
    
    # 6. Re-rank with cross-encoder
    reranked = await rerank(query, combined, top_k=top_k)
    
    # 7. Expand to parent chunks for full context
    context = await expand_parent_chunks(reranked)
    
    return context
```

---

## Knowledge Graph (Vehicle Ontology)

Beyond vector search, we need a **knowledge graph** that understands part relationships:

```
[RZR XP 1000 2024]
    │
    ├── [Engine System]
    │     ├── [Oil Filter] ──part_number──▶ "2522485"
    │     ├── [Oil] ──spec──▶ "PS-4 5W-50, 2.5 qt"
    │     └── [Spark Plug] ──part_number──▶ "3022662"
    │
    ├── [Front Suspension]
    │     ├── [Upper A-Arm LH] ──part_number──▶ "2206026"
    │     │     ├── [Ball Joint] ──part_number──▶ "7081867"
    │     │     ├── [Bushing Kit] ──part_number──▶ "5439874"  
    │     │     └── ──requires_tool──▶ "Ball Joint Press"
    │     │
    │     ├── [CV Axle Front LH] ──part_number──▶ "1334441"
    │     │     ├── [CV Boot Kit] ──part_number──▶ "2206028"
    │     │     └── ──commonly_fails_with──▶ [Wheel Bearing LH]
    │     │
    │     └── [Shock Absorber Front LH]
    │           └── ──torque_spec──▶ "55 ft-lbs"
    │
    └── [Drivetrain]
          ├── [CVT Belt] ──part_number──▶ "3211186"
          │     └── ──commonly_replaced_with──▶ [Clutch Weights]
          └── [Front Diff Fluid] ──spec──▶ "AGL, 10 oz"
```

This graph enables queries like:
- "What else should I replace when doing a CV axle?" → Follow `commonly_fails_with` edges
- "What tools do I need for an A-arm replacement?" → Follow `requires_tool` edges
- "What's the torque spec for the shock mount bolt?" → Direct node lookup

---

*Continue to → [03_AI_AGENT_DESIGN.md](./03_AI_AGENT_DESIGN.md)*
