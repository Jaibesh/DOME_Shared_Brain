
# DOME Knowledge Hub Guide

> "An agent that learns alone, dies alone. An agent that learns together, scales forever."

## 1. Concept
The **Knowledge Hub** (`knowledge_hub/`) is the shared long-term memory for the entire DOME ecosystem. It allows agents to leave "breadcrumbs" for future agents (or future versions of themselves) to follow.

It is broken into three domains:
1.  **Manifests**: "Who exists?" (Discovery)
2.  **Lessons**: "What worked?" (Optimization)
3.  **Patterns**: "How do I do X?" (Standardization)

## 2. Usage for Agent Creators

### A. Registering Your Agent
When you create a new agent, register it so others can find it or handoff tasks to it.
```python
from execution.knowledge_client import get_knowledge_client, AgentManifest

client = get_knowledge_client("MyNewAgent")
manifest = AgentManifest(
    agent_name="MyNewAgent",
    version="1.0.0",
    description="Handles X and Y tasks.",
    core_modules=["customer", "utility"],
    directives_used=["directives/my_agent.md"],
    agent_model_config={"main": "gemini-1.5-pro"}
)
client.register_manifest(manifest)
```

### B. Sharing Insights (Runtime)
Direct your agents to use the `share_insight` tool when:
- They fix a runtime error.
- They find a new user preference pattern.
- They encounter a compliance edge case.

**Example Tool Call:**
```json
{
  "category": "compliance",
  "summary": "Avoid the phrase 'reverse aging'",
  "content": "Users respond better to 'cellular activation'. 'Reverse aging' triggers Policy Rule #4."
}
```

### C. Reading Patterns (Design Time)
Use `client.read_pattern("supervisor_template")` to get standardized code blocks when building new features.

## 3. Best Practices
- **Search First:** Before building a new directive, have your Orchestrator run `search_global_knowledge` to see if another agent has already solved the problem.
- **Tag Generously:** When logging insights, add tags like `["error", "api_v2", "timeout"]` to make search easier.
