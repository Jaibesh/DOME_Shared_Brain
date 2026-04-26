# Pattern: LangGraph Agent Composition

## Definition
Composing multiple sub-agents under a central LangGraph agent to handle different aspects of a task. This allows for modularity and reusability of agent components.

## Details
The Validator tool uses this pattern, with sub-agents for static linting (deterministic) and LLM-based best practice validation. Results from different sub-agents are combined within the LangGraph.

## Related Tags
`LangGraph`, `Agent`, `Composition`, `Modularity`

*Synthesized via AI*
