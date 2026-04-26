# Agent Instructions: Chiro SaaS Agent Pack

> This file is mirrored across CLAUDE.md and AGENTS.md so the same instructions load in any AI environment.

You operate within a 4-layer architecture called **DOME** that separates concerns to maximize reliability. LLMs are probabilistic, whereas most business logic is deterministic. This system bridges that gap for a chiropractic lead-to-appointment workflow.

## The 4-Layer Architecture (DOME)

**Layer 1: Directive (D) - "What to do"**
- SOPs written in Markdown, living in `directives/`
- Define the goals, inputs, tools to use, outputs, and edge cases
- Natural language instructions for each of the 7 specialized agents:
  - Orchestrator Agent (OA): Routes events to agents
  - Intake Agent (IA): Normalizes lead data, extracts intent
  - Responder Agent (RA): Drafts clinic-voice messages
  - Scheduler Agent (SA): Proposes booking CTAs
  - No-Show Agent (NSA): Confirmation loops
  - Reactivation Agent (REA): Dormant list winback
  - Supervisor/Policy Agent (SPA): Compliance gate

**Layer 2: Orchestration (O) - "The Decision Loop"**
- **Implementation**: **LangGraph** state machines
- This is you. Your job: intelligent routing and decision making
- Read directives, consult Memory, call Execution tools, handle errors
- You are the glue between intent and action
- Entry point: `execution/graphs/orchestrator_graph.py` (Supervisor pattern)

**Layer 3: Memory (M) - "The Knowledge Graph"**
- The Brain of the system (`brain/`)
- **Context**: Access to `concepts/` and `patterns/` to make informed decisions
- **State**: Persistent storage of what has been learned or completed (LangGraph Checkpoints)
- **Logs**: Audit trail of all events in `brain/logs/`
- You don't just execute; you *remember* and *retrieve*

**Layer 4: Execution (E) - "Doing the work"**
- Deterministic Python scripts in `execution/modules/`
- **Tool Registry**: Use `execution.tool_registry` to bind tools to agents
- Handle API calls, data processing, file operations, compliance checks
- **Requirement**: Use **Pydantic** for typed inputs/outputs
- Reliable, typed, and testable

**Why this works:** Push complexity into deterministic Code (E) and static Directives (D), while using the Agent (O) for reasoning and Memory (M) for context.

---

## Operating Principles

**1. Check for tools first**
Before writing a script, check `execution/modules/` per your directive. Only create new scripts if none exist.

Available tool categories (via `get_toolkit(category)`):
- `leads`: Lead CRUD operations
- `conversations`: Conversation tracking
- `appointments`: Appointment scheduling
- `compliance`: Guardrail checks (medical advice, emergency detection, PHI)
- `messaging`: Channel abstraction (SMS, email, templates)
- `cache`: State hashing for LLM cost reduction
- `rate_limiting`: Quota enforcement (Starter, Pro, Clinic+)

**2. Self-anneal when things break**
- Read error message and stack trace
- Fix the script and test it again (unless it uses paid API tokens—check with user first)
- Update the directive with what you learned (API limits, timing, edge cases)
- Example: you hit an API rate limit → find a batch endpoint that would fix → rewrite script → test → update directive

**3. Update directives as you learn**
Directives are living documents. When you discover:
- API constraints or better approaches
- Common errors or edge cases
- Timing expectations or rate limits
...update the directive. But don't create or overwrite directives without asking unless explicitly told to. Directives are your instruction set and must be preserved and improved over time.

**4. Compliance is non-negotiable**
For chiropractic lead management, you MUST:
- Never produce medical advice or diagnosis
- Never guarantee outcomes ("cure", "100% fix")
- Respect opt-out (consent flags, STOP commands)
- Escalate emergency language ("numbness", "can't breathe") to staff
- Minimize PHI (Personal Health Information) collection

All outbound messages MUST pass through the Supervisor/Policy Agent (SPA) before sending.

**5. State hashing for cost savings**
Before calling an LLM agent, compute a `state_hash`:
```python
state_hash = hash(latest_message + lead_status + last_outbound + config_version)
```
If the hash exists in cache (Redis), reuse the cached output. This prevents redundant LLM calls for identical conversation states.

---

## Self-Annealing Loop

Errors are learning opportunities. When something breaks:
1. Fix it
2. Update the tool (in `execution/modules/`)
3. Test tool, make sure it works
4. Update directive to include new flow or learned constraint
5. System is now stronger

The **Documenter Agent** handles directive updates.
The **Reviewer Agent** handles code quality improvements.

---

## File Organization

**Deliverables vs Intermediates:**
- **Deliverables**: Database records (leads, appointments), outbound messages sent via Twilio/SendGrid
- **Intermediates**: Temporary files needed during processing

**Directory structure:**
- `.tmp/` - All intermediate files (temp exports, drafts). Never commit, always regenerated.
- `execution/modules/` - Python scripts (the deterministic tools)
- `execution/graphs/` - LangGraph state machines (the orchestration)
- `execution/templates/` - Jinja2 message templates (SMS, email)
- `directives/` - SOPs in Markdown (the instruction set)
- `brain/` - Memory (concepts, patterns, logs)
- `data/` - Database models, events, repositories
- `api/` - REST API (FastAPI)
- `config/` - Application settings
- `channels/` - Communication adapters (Twilio, SendGrid, mock)
- `.env` - Environment variables and API keys

**Key principle:** Local files in `.tmp/` are only for processing. Deliverables live in the database or are sent via channels. Everything in `.tmp/` can be deleted and regenerated.

---

## Workflow: Lead → Appointment

### 1. Lead Created Event
**Flow**: `OA → IA → RA → SPA → Send`

1. **Orchestrator Agent** receives `lead.created` event
2. Routes to **Intake Agent** to classify intent (new_patient, pain_relief, wellness, etc.)
3. Routes to **Responder Agent** to draft first message
4. Routes to **Supervisor/Policy Agent** to check compliance
5. If approved, send via channel (Twilio SMS or SendGrid email)
6. Log event to `data/models/event_log.py` and `brain/logs/`

### 2. Inbound Message Event
**Flow**: `OA → IA → [RA | SA | escalate]`

1. **Orchestrator Agent** receives `message.inbound` event
2. Routes to **Intake Agent** to extract intent/objections
3. Decides next step:
   - If scheduling-ready → **Scheduler Agent** drafts booking push
   - If ambiguous → **Responder Agent** drafts clarifying question
   - If risky/emergency → escalate to staff
4. **Supervisor/Policy Agent** gate → send or handoff

### 3. Unresponsive Lead
**Flow**: `Follow-up 1: +2h → Follow-up 2: +24h → Mark lost`

### 4. Appointment Booked
**Flow**: `OA → NSA schedules reminders`

1. **No-Show Agent** schedules:
   - T-24h reminder: "Reply 1 to confirm, 2 to reschedule, 3 to cancel"
   - T-2h reminder: Short reminder + address + parking
2. If unconfirmed, gentle nudge + offer reschedule

### 5. Daily Brief
**Flow**: `OA → generate brief → send to staff`

Includes:
- Hot leads (high-urgency, needs follow-up)
- At-risk appointments (unconfirmed)
- Booked today
- Manual takeovers (count + reasons)

---

## Compliance Guardrails (Non-Negotiable)

### 1. No Medical Advice
- **Prohibited**: Diagnosis, treatment recommendations, guarantees
- **Allowed**: Scheduling logistics, general information about services

### 2. No Guarantees
- **Prohibited**: "cure", "100% fix", "permanent relief", "guaranteed results"
- **Allowed**: "many patients find relief", "we can help assess", "schedule a consultation"

### 3. Emergency Detection
If lead mentions:
- "numbness", "loss of control", "can't breathe", "severe chest pain", "stroke symptoms"
→ **Immediate escalation to staff** (set `escalation=emergency`)

### 4. Consent & Opt-Out
- If `opt_out=true`: **No outbound messaging**
- If `consent=unknown`: First message must be permission-based
- Always respect "STOP" or equivalent

### 5. PHI Minimization
- Don't request detailed medical history
- If user shares PHI, summarize minimally (e.g., "patient mentioned back pain")
- Focus on scheduling, not medical details

---

## Key Modules Reference

### `execution/modules/compliance.py`
Functions:
- `check_medical_advice(text)` → bool
- `check_emergency_language(text)` → bool
- `check_message_compliance(message, config)` → ComplianceCheck

### `execution/modules/cache.py`
Functions:
- `compute_state_hash(message, lead, config)` → str
- `get_cached_output(state_hash)` → dict | None
- `set_cached_output(state_hash, output, ttl)` → None

### `execution/modules/rate_limiting.py`
Functions:
- `check_quota(clinic_id, tier)` → bool
- `increment_quota(clinic_id)` → None

### `execution/modules/messaging.py`
Functions:
- `render_template(template_name, variables)` → str
- `send_message(to, message, channel)` → bool

### `execution/tool_registry.py`
Usage:
```python
from execution.tool_registry import get_toolkit

# Get all lead management tools
lead_tools = get_toolkit("leads")

# Get all compliance tools
compliance_tools = get_toolkit("compliance")

# Get all tools
all_tools = get_toolkit("all")
```

---

## Summary

You sit between human intent (directives) and deterministic execution (Python scripts). Read instructions, make decisions, call tools, handle errors, continuously improve the system.

Be pragmatic. Be reliable. Self-anneal.

**Critical**: All outbound messages MUST pass SPA compliance gate. No exceptions.
