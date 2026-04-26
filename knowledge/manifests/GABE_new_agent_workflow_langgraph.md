# Workflow: Building a New Agent (LangGraph Edition)

This directive outlines the standard process for creating a new DOME Agent using LangGraph.

## Phase 1: Define the Interface (Pydantic)
1.  **Input Schema**: What does the agent take? (e.g., `TranscriptInput`)
2.  **Output Schema**: What does the agent return? (e.g., `AnalysisResult`)
3.  **State**: What needs to be remembered between steps? (e.g., `AgentState(TypedDict)`)

## Phase 2: Implement Execution Tools (Deterministic)
1.  Create `execution/<agent_name>.py`.
2.  Write pure Python functions for the hard work (APIs, Math, File I/O).
3.  **Crucial**: Wrap these functions in Pydantic models.
    ```python
    def calculate_roi(data: FinancialData) -> ROIMetrics:
        ...
    ```

## Phase 3: Orchestrate (LangGraph)
1.  Define the `StateGraph`.
2.  Add **Nodes** that call your Execution tools.
3.  Add **Conditional Edges** for logic (loops, retries, checks).
4.  Add a **Checkpointer** (`MemorySaver` or `SqliteSaver`) for persistence.

## Phase 4: Directive
1.  Create `directives/<agent_name>.md`.
2.  Describe the "Goal" and "Policy" for the Orchestrator.
3.  Reference the graph entry point.

## Example Structure
```python
# execution/my_agent.py

# 1. State
class MyState(TypedDict):
    input: str
    result: Optional[str]

# 2. Nodes
def step_1(state: MyState):
    return {"result": "processed"}

# 3. Graph
workflow = StateGraph(MyState)
workflow.add_node("step_1", step_1)
workflow.set_entry_point("step_1")
app = workflow.compile(checkpointer=MemorySaver())
```
