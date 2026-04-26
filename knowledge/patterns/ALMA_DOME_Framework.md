# Pattern: DOME Framework (Directive, Orchestration, Memory, Execution)

## Definition
The **DOME Framework** is an evolution of the 3-layer DOE architecture, explicitly adding **Memory** as a core component. It is a blueprint for building autonomous, reliable, and self-improving AI agents.

## The 4 Pillars

### 1. Directive (D)
*The Instruction Set.*
- **What**: Static Markdown files (SOPs).
- **Role**: Provides the "Goal" and "Policy".
- **Example**: `directives/operations_management.md`.

### 2. Orchestration (O)
*The Decision Engine.*
- **What**: The AI Agent (LLM) loop.
- **Role**: Plans, routes, handles errors, and reflects.
- **Key Pattern**: ReAct or LangGraph state machines.

### 3. Memory (M)
*The Context & State.*
- **What**: The Knowledge Graph (`brain/`) and persistent state.
- **Role**: Stores Concepts, Patterns, and historical decisions.
- **Example**: `brain/concepts/`, `brain/patterns/`.

### 4. Execution (E)
*The Hands.*
- **What**: Deterministic Code (Python).
- **Role**: Interacts with the world (API, File System).
- **Key Requirement**: **Pydantic**-typed inputs/outputs for 100% reliability.

## Why DOME?
Adding **Memory** explicitly prevents the agent from starting from scratch every time. It allows for "Compound Learning" where new insights (`brain/concepts`) make future orchestration smarter.

## Related Tags
`Framework`, `Agent Architecture`, `Reliability`, `Memory`

## Application to Beh Brothers Electric
- **Directives**: `operations_management.md`, `service_upgrade.md`
- **Orchestration**: LangGraph agents using `tool_registry.py`
- **Memory**: `brain/sources/` (customers, jobs, price_book), `brain/patterns/`
- **Execution**: `execution/modules/` with Pydantic models
