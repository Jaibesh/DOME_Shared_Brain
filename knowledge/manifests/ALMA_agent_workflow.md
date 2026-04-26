# Workflow: Building a New Agent (LangGraph Edition)

This directive outlines the standard process for creating a new DOME Agent using LangGraph.

## Phase 1: Define the Interface (Pydantic)
1.  **Input Schema**: What does the agent take? (e.g., `CustomerInput`)
2.  **Output Schema**: What does the agent return? (e.g., `CustomerRecord`)
3.  **State**: What needs to be remembered between steps? (e.g., `AgentState(TypedDict)`)

## Phase 2: Implement Execution Tools (Deterministic)
1.  Create `execution/modules/<new_module>.py`.
2.  Write pure Python functions for the hard work (APIs, Math, File I/O).
3.  **Crucial**: Wrap these functions in Pydantic models.
    ```python
    def calculate_estimate(job_input: JobInput) -> Estimate:
        ...
    ```
4.  Register in `execution/tool_registry.py`:
    ```python
    elif category == "new_module":
        candidates = [new_module.function1, new_module.function2]
    ```

## Phase 3: Orchestrate (LangGraph)
1.  Copy template from `execution/templates/template_agent.py`.
2.  Define the `StateGraph` with your custom state.
3.  Add **Nodes** that call your Execution tools via `ToolNode`.
4.  Add **Conditional Edges** for logic (loops, retries, checks).
5.  Add a **Checkpointer** (`MemorySaver` or `SqliteSaver`) for persistence.

## Phase 4: Create Directive
1.  Create `directives/<new_agent>.md`.
2.  Describe the "Goal" and "Policy" for the Orchestrator.
3.  Reference the tools and workflow.

## Example: Customer Service Agent
```python
# execution/agents/customer_agent.py

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from execution.tool_registry import get_toolkit

# State
class CustomerAgentState(TypedDict):
    messages: Annotated[List[str], operator.add]
    customer_id: Optional[str]

# Tools
tools = get_toolkit("customer")
tool_node = ToolNode(tools)

# Graph
workflow = StateGraph(CustomerAgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)
workflow.set_entry_point("agent")
app = workflow.compile(checkpointer=MemorySaver())
```

## Related Files
- `execution/templates/template_agent.py` - Starter template
- `execution/tool_registry.py` - Tool registration
- `brain/patterns/LangGraph_Agent_Composition.md` - Composition pattern
