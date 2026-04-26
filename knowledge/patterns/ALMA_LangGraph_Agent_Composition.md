# Pattern: LangGraph Agent Composition

## Definition
Composing multiple sub-agents under a central LangGraph agent to handle different aspects of a task. This allows for modularity and reusability of agent components.

## Architecture
```
┌─────────────────────────────────────────┐
│           Supervisor Agent              │
│  (Routes requests to appropriate agent) │
└──────────┬──────────┬──────────┬────────┘
           │          │          │
    ┌──────┴──┐  ┌────┴────┐  ┌──┴──────┐
    │Customer │  │   Job   │  │Estimate │
    │  Agent  │  │  Agent  │  │  Agent  │
    └─────────┘  └─────────┘  └─────────┘
```

## Application to Beh Brothers
- **Customer Agent**: Uses `get_toolkit("customer")` for customer CRUD
- **Job Agent**: Uses `get_toolkit("job")` for job lifecycle
- **Estimate Agent**: Uses `get_toolkit("estimate")` for pricing/invoicing
- **Supervisor**: Routes based on user intent

## Benefits
1. **Separation of Concerns**: Each agent focuses on one domain
2. **Reusability**: Agents can be used independently or composed
3. **Testability**: Individual agents can be tested in isolation
4. **Scalability**: Add new agents without modifying existing ones

## Implementation
See `execution/templates/template_agent.py` for starter code.

## Related Tags
`LangGraph`, `Agent`, `Composition`, `Modularity`
