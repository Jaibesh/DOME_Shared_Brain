# System-Wide Agent Instructions

This repository contains Personal Agents built on the DOME 2.0 framework.

## Core Principles
1. **Deterministic Execution**: Agents should prefer deterministic tools over LLM hallucination.
2. **Explicit Routing**: The Supervisor is the single source of truth for routing.
3. **Structured Output**: Tools should return structured data (dictionaries, Pydantic models) where possible.
