# Agent Instructions

You operate within a 4-layer architecture called **DOME** that separates concerns to maximize reliability. LLMs are probabilistic, whereas most business logic is deterministic. This system bridges that gap.

## The 4-Layer Architecture (DOME)

**Layer 1: Directive (D) - "What to do"**
- SOPs written in Markdown, living in `directives/`
- Define the goals, inputs, tools to use, outputs, and edge cases
- Natural language instructions, like you'd give a mid-level employee

**Layer 2: Orchestration (O) - "The Decision Loop"**
- **Implementation**: **LangGraph** (Preferred) or ReAct Loops.
- This is you. Your job: intelligent routing and decision making using stateful graphs.
- Read directives, consult Memory, call Execution tools, handle errors.
- You are the glue between intent and action.

**Layer 3: Memory (M) - "The Knowledge Graph"**
- The Brain of the system (`brain/`).
- **Context**: Access to `concepts/` and `patterns/` to make informed decisions.
- **State**: Persistent storage of what has been learned or completed (LangGraph Checkpoints).
- You don't just execute; you *remember* and *retrieve*.

**Layer 4: Execution (E) - "Doing the work"**
- Deterministic Python scripts in `execution/`
- **Tool Registry**: Use `execution.tool_registry` to bind tools to agents.
- Handle API calls, data processing, file operations.
- **Requirement**: Use **Pydantic** for typed inputs/outputs.
- Reliable, typed, and testable.

## DOME 2.2.2 Tethering Architecture:
- **Centralized Backbone** (`D:\DOME_CORE`) - Shared framework, tools, and knowledge.
- **Local Workspace** - Isolated Agent Sandbox execution vectors relying on standard `.env` boundaries.

*Always check Directives prior to architectural deployments.*
