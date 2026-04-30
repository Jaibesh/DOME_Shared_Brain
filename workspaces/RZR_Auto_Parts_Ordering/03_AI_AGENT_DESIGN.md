# 03 — AI Agent Design

## Agent Architecture — Agentic RAG with Tool Calling

The AI agent is NOT a simple chatbot. It's an **agentic system** that can reason, use tools, and orchestrate multi-step workflows.

```
                    ┌──────────────────────────┐
                    │     Agent Orchestrator    │
                    │     (Gemini 2.5 Pro)      │
                    │                          │
                    │  • Classifies query      │
                    │  • Plans tool usage      │
                    │  • Synthesizes response   │
                    └─────────┬────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
         ┌────▼────┐   ┌─────▼─────┐   ┌─────▼─────┐
         │ Search  │   │  Parts    │   │ Schematic │
         │ Manual  │   │  Lookup   │   │ Retriever │
         │ Tool    │   │  Tool     │   │ Tool      │
         └─────────┘   └───────────┘   └───────────┘
              │               │               │
              ▼               ▼               ▼
        Vector DB +     Parts Catalog    Image Store +
        Knowledge       (Supabase)       VLM Analysis
        Graph
```

---

## Tool Definitions

The agent has access to these tools via Gemini function calling:

### Tool 1: `search_service_manual`
```python
def search_service_manual(
    query: str,
    vehicle_model: str,
    model_year: int,
    content_type: str = "all"  # procedure, specification, diagram, parts_list
) -> list[dict]:
    """Search the service manual knowledge base.
    Returns relevant sections with page references."""
```

### Tool 2: `lookup_parts`
```python
def lookup_parts(
    assembly_category: str,    # e.g., "Front Suspension"
    component: str,            # e.g., "CV Axle"
    vehicle_model: str,
    model_year: int,
    include_related: bool = True  # also return commonly co-replaced parts
) -> list[dict]:
    """Look up OEM part numbers from the parts catalog.
    Returns part numbers, names, prices, and availability."""
```

### Tool 3: `get_schematic`
```python
def get_schematic(
    assembly_category: str,
    vehicle_model: str,
    model_year: int
) -> dict:
    """Retrieve the exploded assembly diagram for a specific system.
    Returns image URL and annotated component list."""
```

### Tool 4: `get_related_parts`
```python
def get_related_parts(
    part_number: str
) -> list[dict]:
    """Query knowledge graph for related/co-replaced parts.
    Returns parts that are commonly replaced together."""
```

### Tool 5: `check_repair_history`
```python
def check_repair_history(
    vehicle_id: str,
    system: str = None
) -> list[dict]:
    """Check previous repairs on this vehicle.
    Helps avoid duplicate work and identify recurring issues."""
```

---

## System Prompt

```
You are the DOME Fleet Mechanic AI — an expert Polaris UTV technician with deep 
knowledge of every vehicle in the Epic 4x4 Adventures fleet.

## Your Role
You assist mechanics by diagnosing damage, providing repair procedures from 
official Polaris service manuals, identifying the exact OEM parts needed, and 
generating parts orders.

## Core Principles
1. **NEVER invent part numbers.** Only use part numbers from the parts_catalog 
   database. If you cannot find a part number, say so explicitly.
2. **Always cite your sources.** Reference the specific service manual section, 
   page number, and diagram when providing procedures.
3. **Think like a senior tech.** When a mechanic reports damage to one component, 
   proactively suggest inspecting related components that commonly fail together.
4. **Be VIN-specific.** Different model years have different part numbers. Always 
   verify the vehicle's exact year and trim before quoting parts.
5. **Safety first.** Always include torque specifications, required fluids, and 
   safety warnings from the service manual.

## Response Format for Damage Reports
When a mechanic describes damage, respond with:

### 1. Diagnosis Summary
Brief analysis of the reported damage and likely root cause.

### 2. Repair Procedure
Step-by-step instructions from the service manual, including:
- Required tools
- Safety precautions
- Estimated labor time

### 3. Parts Required
A structured parts list:
| Part Number | Description | Qty | Category |
Each part must come from the verified parts catalog.

### 4. Related Inspections
Other components to check while the vehicle is disassembled.

### 5. Schematics
Reference the relevant exploded diagram(s).

## Current Vehicle Context
{vehicle_context}  // Injected at runtime with VIN, model, year, mileage, history
```

---

## Conversation Flow Design

### Phase 1: Vehicle Selection
```
Mechanic: [Selects RZR-07 from dropdown]
System:  Loaded RZR-07 — 2024 RZR XP 1000 Premium (VIN: 3NSRZE999RF123456)
         Current mileage: 4,230 mi
         Last service: Belt replacement @ 3,800 mi (2026-03-15)
         
         What happened to this vehicle?
```

### Phase 2: Damage Description & Diagnosis
```
Mechanic: "Front left CV axle is busted. Boot was ripped and the joint is 
          grinding. Also noticed the wheel has some play in it."

AI Agent: [Internal reasoning]
         → Tool call: search_service_manual("CV axle replacement front left", 
                                            "RZR XP 1000", 2024)
         → Tool call: lookup_parts("Front Drivetrain", "CV Axle Front LH",
                                   "RZR XP 1000", 2024, include_related=True)
         → Tool call: get_schematic("Front Drivetrain", "RZR XP 1000", 2024)
         → Tool call: check_repair_history("RZR-07", "Front Suspension")

AI Response:
         ## Diagnosis
         The ripped CV boot allowed debris and water into the joint, causing 
         the grinding you're hearing — classic CV joint failure. The wheel 
         play you're noticing likely indicates the wheel bearing is also 
         damaged, which is common when a CV joint fails catastrophically 
         (metal debris migrates into the bearing).

         ## Repair Procedure
         📖 Service Manual Reference: Chapter 7, Section 7.3 "Front Drive 
         Axle Removal/Installation" (p. 245-249)
         
         ### Required Tools
         - Socket set (10mm, 14mm, 17mm, 21mm, 36mm)
         - Torque wrench (20-100 ft-lb range)
         - Ball joint separator
         - Snap ring pliers
         - Axle nut socket (36mm)
         
         ### Procedure
         1. Secure vehicle on level surface, engage parking brake
         2. Remove front left wheel (lug nuts: 120 ft-lbs)
         3. Remove cotter pin and axle nut (torque: 155 ft-lbs)
         4. Disconnect lower ball joint from knuckle
         [... full procedure from manual ...]

         ## Parts Required
         | Part # | Description | Qty | Est. Price |
         |--------|-------------|-----|-----------|
         | 1334441 | CV Axle Assembly, Front LH | 1 | $289.99 |
         | 3514699 | Wheel Bearing, Front | 1 | $45.99 |
         | 7042430 | Cotter Pin Kit | 1 | $4.99 |
         | 5412189 | Axle Nut, Front | 1 | $8.99 |
         
         ## Recommended Additional Inspections
         ⚡ Since the CV joint failed catastrophically, check:
         - Front left A-arm for cracks/bending (debris may have caused impact)
         - CV boot on front RIGHT side (if one went, the other may be wearing)
         
         📐 [Schematic: Front Drivetrain Exploded View]
```

### Phase 3: Parts Review & Order
```
Mechanic: "That looks right. Also add a CV boot kit for the right side as 
          a preventive measure."

AI Agent: → Tool call: lookup_parts("Front Drivetrain", "CV Boot Kit Front RH",
                                     "RZR XP 1000", 2024)

AI Response:
         Added to parts list:
         | 2206028 | CV Boot Kit, Front RH | 1 | $24.99 |
         
         Updated total: 5 parts, estimated $374.95
         
         Ready to submit this order? You can edit quantities or remove items 
         in the parts panel on the right. →
```

---

## Safety Guardrails

### 1. Part Number Validation
```python
async def validate_part_number(part_number: str, vehicle_model: str, year: int) -> bool:
    """Verify a part number exists in our catalog AND fits this vehicle."""
    result = await supabase.table('parts_catalog').select('*').eq(
        'part_number', part_number
    ).contains('vehicle_models', [vehicle_model]).contains(
        'model_years', [year]
    ).execute()
    return len(result.data) > 0
```

### 2. Hallucination Prevention
- LLM output is post-processed: every part number in the response is validated against `parts_catalog`
- If a part number doesn't exist, it's flagged and removed with a warning
- The agent CANNOT generate part numbers — only retrieve them from the database

### 3. Confidence Scoring
```python
# If retrieval confidence is low, the agent asks clarifying questions
if max_retrieval_score < 0.75:
    return "I'm not 100% certain about this diagnosis. Can you provide more 
            details? Specifically: [targeted questions based on partial matches]"
```

---

*Continue to → [04_PARTS_ORDERING.md](./04_PARTS_ORDERING.md)*
