# 08 — Plan Supplement: Gaps, Enhancements & Critical Additions

> This document addresses gaps identified during a critical audit of the original plan (docs 00-07). Everything here should be considered **part of the canonical plan**.

---

## Critical Context: Polaris Sponsorship & Partnership

Epic 4x4 Adventures is an **official Polaris partner/sponsor**. This has major implications:

### Advantages This Unlocks
| Advantage | Impact on Plan |
|-----------|---------------|
| **Dealer portal access** (polarisdealers.com) | Tier 2 ordering automation is the **default path**, not a stretch goal |
| **Official service manuals** | May be available free/discounted through partnership — confirm with Polaris rep |
| **Technical Service Bulletins** | Direct access to TSBs and recall notices through dealer portal |
| **Parts pricing & availability** | Real-time dealer-level pricing, not retail markup |
| **Polaris rep relationship** | Can ask about API access, data feeds, or integration support directly |
| **OEM-only parts policy** | Simplifies the parts catalog — single source of truth, no cross-referencing needed |

### Action Items Before Development
1. **Contact your Polaris rep** and ask specifically:
   - Do they offer any API or data feed for parts catalog data?
   - Can they provide service manuals in digital format?
   - Are there integration tools available through their partnership program?
   - Would they be open to this project as a case study / co-development?
2. **Confirm dealer portal credentials** — username and access level for polarisdealers.com
3. **Catalog the exact service manuals** you already have vs. need to acquire

> This partnership potentially eliminates the #1 risk in the original plan (no public API). Polaris may actually *want* to help build this.

---

## Gap 1: Parts Availability & Backorder Handling (MISSING from original plan)

Even with a Polaris partnership, OEM parts can be backordered. The AI must handle this gracefully.

### What to Add

#### Availability Intelligence
```python
class PartAvailabilityChecker:
    """Check real-time OEM availability through dealer portal."""
    
    async def check_availability(self, part_number: str) -> AvailabilityResult:
        # Check Polaris dealer portal for stock status
        portal_result = await self.check_polaris_dealer_portal(part_number)
        
        # Check our own shop inventory
        local_result = await self.check_local_inventory(part_number)
        
        return AvailabilityResult(
            part_number=part_number,
            in_stock_local=local_result.quantity,
            polaris_available=portal_result.available,
            estimated_ship_date=portal_result.ship_date,
            polaris_warehouse=portal_result.warehouse_location
        )
```

#### AI Response When Parts Backordered
1. Alert the mechanic: "⚠️ Part #1334441 is currently backordered (est. 2-3 weeks)"
2. Suggest whether the vehicle can still operate safely without the repair
3. Propose repair triage if multiple vehicles need the same scarce part
4. Notify via Slack so ops can plan around downtime

---

## Gap 2: Evaluation & Quality Assurance Framework (INCOMPLETE in original)

The original plan mentions "30 test queries" in Phase 1 but lacks rigor. For safety-critical repair guidance, this is inadequate.

### Production Evaluation Framework

#### Golden Dataset Requirements
Build a minimum of **100 curated test cases** across these categories:

| Category | # Cases | Example |
|----------|---------|---------|
| Simple part lookup | 20 | "What's the part number for a 2024 RZR XP 1000 drive belt?" |
| Damage diagnosis | 20 | "Front end clunking over bumps, RZR-07" |
| Multi-part repair | 20 | "Complete front suspension rebuild, what do I need?" |
| Schematic retrieval | 15 | "Show me the front differential exploded view" |
| Edge cases / negatives | 15 | "Can I use a 2023 CV axle on a 2024?" |
| Safety-critical | 10 | "Brake procedure for rear caliper replacement" |

#### Metrics to Track

| Metric | Target | Tool |
|--------|--------|------|
| **Context Recall** | ≥ 95% | RAGAS |
| **Context Precision** | ≥ 90% | RAGAS |
| **Faithfulness** | ≥ 98% | RAGAS |
| **Answer Correctness** | ≥ 95% | Human review |
| **Part Number Accuracy** | **100%** | Automated DB check |
| **Hallucination Rate** | **0%** | Automated + human |

#### CI/CD Quality Gate
```python
def test_rag_quality():
    results = evaluate_golden_dataset("tests/golden_100.json")
    
    assert results.faithfulness >= 0.98
    assert results.context_recall >= 0.95
    assert results.part_number_accuracy == 1.0, "CRITICAL: Invalid part numbers"
    assert results.hallucination_count == 0, "CRITICAL: Hallucinated content"
```

#### Continuous Production Monitoring
- Sample 10% of production conversations for automated evaluation
- Weekly human review of flagged low-confidence responses
- Monthly full golden dataset regression
- Mechanic feedback (👍/👎) on every AI response → feeds back into golden dataset

---

## Gap 3: Fine-Tuning Strategy (NOT ADDRESSED in original)

### Recommended Phased Approach

**Phase 1-2: RAG Only** (start here)
- Faster to build, easier to maintain, citations built-in

**Phase 3+: Add Fine-Tuning** (once we have production data)
- Fine-tune on 500+ real mechanic conversations to teach:
  - Fleet-specific jargon ("it's grenading" = catastrophic failure)
  - Preferred output format
  - Diagnostic reasoning patterns for rental fleet abuse
- Use LoRA fine-tuning on Gemini or open-source model

### Data Collection From Day 1
```sql
CREATE TABLE conversation_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES repair_sessions(id),
    role TEXT NOT NULL,                  -- 'user' or 'assistant'
    content TEXT NOT NULL,
    tool_calls JSONB,
    retrieval_context JSONB,
    mechanic_feedback TEXT,             -- 'positive', 'negative', 'corrected'
    correction_text TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## Gap 4: Shop Inventory Tracking (Phase 4 → promote to Phase 2)

### Minimum Viable Inventory System
```sql
CREATE TABLE shop_inventory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    part_number TEXT NOT NULL,
    part_name TEXT NOT NULL,
    quantity_on_hand INTEGER DEFAULT 0,
    quantity_reserved INTEGER DEFAULT 0,
    reorder_threshold INTEGER DEFAULT 2,
    last_restocked TIMESTAMPTZ,
    shelf_location TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

#### AI Integration
When generating a parts list, check inventory first:
- "✅ CV Boot Kit (2206028) — **1 in stock** (Shelf B-3)"
- "⚠️ CV Axle (1334441) — **0 in stock** — needs ordering"

---

## Gap 5: MPOWR Work Order Integration (MENTIONED but no detail)

### Automatic Flow
```
AI creates repair session → Mechanic approves parts list
    │                              │
    │                              ├──▶ Parts order → Polaris dealer portal
    │                              │
    └──────────────────────────────└──▶ MPOWR work order created automatically
                                        (via existing Service Bot infrastructure)
                                        - Vehicle linked
                                        - Service tasks from AI diagnosis
                                        - Expected hours from service manual
                                        - Parts list attached
```

---

## Gap 6: Data Freshness & Maintenance Plan (INCOMPLETE)

### Maintenance Schedule

| Task | Frequency | Method |
|------|-----------|--------|
| Parts catalog price sync | Weekly | Dealer portal scraper |
| Part supersession check | Weekly | Compare against stored part numbers |
| New TSB ingestion | Monthly | Check dealer portal for new bulletins |
| New model year ingestion | Annually (Sept-Oct) | Purchase new manuals, full pipeline run |
| Knowledge graph validation | Quarterly | Human review with lead mechanic |
| Golden dataset expansion | Monthly | Add edge cases from production |

### Supersession Handling
When Polaris supersedes a part number (old → new):
1. Update `parts_catalog.superseded_by`
2. Add new part number
3. Update knowledge graph nodes
4. Re-embed affected chunks
5. Log for audit

---

## Gap 7: Offline / Low-Connectivity Mode

### PWA Strategy
- Cache recent vehicle profiles and common procedures
- Queue chat messages offline, sync when connected
- Cache top 50 most-ordered parts with pricing
- Schematics cached per vehicle after first view
- **Full AI chat requires connectivity** (no offline LLM on a laptop)

---

## Updated Prerequisites (Revised)

Given the Polaris partnership, the prerequisite list simplifies:

| Question | Original Status | Updated Status |
|----------|----------------|----------------|
| Polaris dealer credentials? | Unknown | **Likely YES** — confirm access level |
| Service manuals available? | Need to purchase | **May be provided** — ask Polaris rep |
| Fleet VINs? | Need from user | Still needed |
| Cloud provider? | GCP recommended | Still need confirmation |
| Budget (~$75-120/mo)? | Need approval | Still need confirmation |
| **NEW: Polaris API/data feed?** | — | **Ask rep** — could eliminate portal scraping entirely |
