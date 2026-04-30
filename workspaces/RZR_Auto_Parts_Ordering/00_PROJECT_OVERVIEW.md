# 🔧 Polaris AI Mechanic Assistant — Project Master Plan

> **Project Codename:** RZR AutoParts AI  
> **Status:** Planning Phase  
> **Created:** 2026-04-28  
> **Author:** DOME Engineering  

---

## Table of Contents (Multi-Document Plan)

| # | Document | Description |
|---|----------|-------------|
| 00 | **PROJECT_OVERVIEW.md** (this file) | Vision, goals, success criteria, fleet inventory |
| 01 | **ARCHITECTURE.md** | System architecture, tech stack, data flow diagrams |
| 02 | **KNOWLEDGE_ENGINE.md** | Document ingestion, RAG pipeline, vector DB, knowledge graph |
| 03 | **AI_AGENT_DESIGN.md** | Chat agent design, prompt engineering, repair reasoning |
| 04 | **PARTS_ORDERING.md** | Parts catalog, ordering automation, Polaris portal integration |
| 05 | **FRONTEND_UX.md** | Web app UI/UX, vehicle selector, chat interface, parts editor |
| 06 | **CLOUD_DEPLOYMENT.md** | Cloud hosting, security, access control, DevOps |
| 07 | **IMPLEMENTATION_ROADMAP.md** | Phased timeline, milestones, budget estimates, risks |
| 08 | **PLAN_SUPPLEMENT.md** | Critical gaps: aftermarket parts, backorders, evaluation, fine-tuning, inventory, offline |

---

## 1. Project Vision

Build a **cloud-hosted AI mechanic assistant** that enables any technician in the fleet to:

1. **Select a vehicle** from the fleet (by unit ID, VIN, or model)
2. **Describe the damage** in natural language via a chat interface
3. **Receive an AI-generated repair plan** including:
   - Step-by-step repair procedures from official service manuals
   - Relevant schematics and exploded diagrams
   - A complete parts list with OEM part numbers and quantities
4. **Review and edit** the parts list in a clean, editable document
5. **Submit the order** through the Polaris parts ordering system

The AI must have a **deep mechanical understanding** of how every Polaris vehicle in the fleet is assembled, maintained, and repaired — equivalent to a senior Polaris-certified technician.

---

## 2. Business Goals

| Goal | Metric |
|------|--------|
| Reduce parts ordering time | From ~45 min manual lookup → <5 min AI-assisted |
| Eliminate wrong-part orders | Target <2% error rate on part numbers |
| Standardize repair procedures | 100% of repairs follow OEM service manual protocol |
| Reduce vehicle downtime | Faster diagnosis → faster parts arrival → faster repair |
| Enable any mechanic to work on any vehicle | No tribal knowledge dependency |

---

## 3. Fleet Inventory (Vehicles to Support)

Based on Epic 4x4 Adventures fleet composition:

| Vehicle Model | Configuration | Trim | Color |
|---------------|---------------|------|-------|
| **2026 RZR Pro R** | 2-seat | Ultimate | Indy Red |
| **2026 RZR Pro S** | 2-seat | Ultimate | Warm Grey |
| **2026 RZR Pro S** | 4-seat | Ultimate | Warm Grey |
| **2026 RZR XP S** | 2-seat | Ultimate | Stealth Grey |
| **2026 RZR XP S** | 4-seat | Ultimate | Stealth Grey |

> **Note:** Each model year may have different part numbers. The system must be VIN-aware to handle year-specific and trim-specific variations.

---

## 4. Common Damage Patterns (Rental Fleet)

Research confirms these are the highest-frequency repair categories for rental RZR fleets:

### Tier 1 — Very High Frequency
- **CV Axles & CV Joints** — Torn boots, broken axles from aggressive riding
- **CVT Drive Belt** — Overheating, abuse, improper gear selection
- **Windshields & Body Panels** — Debris impact, rollovers

### Tier 2 — High Frequency  
- **A-Arms & Suspension** — Bent from rock impacts, worn bushings/ball joints
- **Wheel Bearings** — Accelerated wear in mud/dust/water
- **Radiator & Cooling** — Clogged with mud, punctured coolant lines

### Tier 3 — Moderate Frequency
- **Tie Rods & Steering** — Impact damage, worn ends
- **Brake Components** — Pads, rotors, calipers from aggressive use
- **Electrical** — Wiring harness damage, sensor failures

The AI must be especially proficient at diagnosing and generating parts lists for Tier 1 and Tier 2 categories.

---

## 5. Success Criteria

### MVP (Phase 1)
- [ ] Mechanic can select any fleet vehicle and describe damage
- [ ] AI returns correct repair procedure from service manual
- [ ] AI generates accurate parts list with OEM part numbers
- [ ] Parts list is editable before submission
- [ ] Application accessible from any laptop on the network

### Production (Phase 2)
- [ ] Automated ordering through Polaris dealer portal
- [ ] Schematics/exploded diagrams displayed inline

### Advanced (Phase 3)
- [ ] Parts inventory tracking
- [ ] Cost estimation and budget tracking

---

## 6. Key Constraints & Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Polaris has no public API for parts ordering | High | Playwright automation of dealer portal (proven pattern in DOME) |
| Service manuals are PDF-only, no digital format | High | Multimodal RAG with vision models for schematic understanding |
| Part number supersessions change frequently | Medium | Regular catalog sync + dealer portal validation |
| AI hallucination on part numbers | Critical | Constrained generation from indexed catalog only, never invented |
| Mechanic descriptions may be vague | Medium | Guided chat flow with clarifying questions |

---

*Continue to → [01_ARCHITECTURE.md](./01_ARCHITECTURE.md)*
