# Agent Cross-Workspace Synchronization
> How knowledge and tools flow between disparate DOME environments.

## 1. Knowledge Sharing (Lessons & Insights)
When an agent calls the `share_insight` tool, the `KnowledgeClient` performs a **Dual-Write**:
1.  **Local Log:** Written to `./knowledge_hub/` within the workspace (for low-latency access).
2.  **Global Log:** Appended to `G:\DOME_CORE\knowledge\lessons\{category}_log.jsonl`.

When an agent calls `search_global_knowledge`, it queries the Global Log on the Gamedrive, allowing it to "recall" things it never personally experienced.

## 2. Tool Sharing (The Tool Library)
The DOME framework is being updated to support **Dynamic Tool Resolution**:
- If an agent requests a tool category not found locally, the system checks `G:\DOME_CORE\tools\`.
- If a matching `.py` file is found, it is dynamically imported during agent initialization.

**Standardized Tool Schema:**
To be shareable, a tool file in the CNS library should look like this:
```python
# G:\DOME_CORE\tools\universal_scrapers.py
from langchain_core.tools import tool

@tool
def power_search(query: str):
    """Deep search across three search engines."""
    # Implementation...
    return results
```

## 3. Persistent Memory Sync
The `TenantMemoryStore` is mapped to the Gamedrive for **Cold Memory**:
- **Hot Memory (Short Term):** Stored in local JSON/SQLite for sub-millisecond speeds.
- **Cold Memory (Long Term):** Stored in FAISS indexes on `G:\DOME_CORE\memory\cold\{tenant_id}`.

**Migration Warning:** If you move a workspace to a new computer, simply plug in the Gamedrive and set the environment variable. Your agents will retain their full "personality" and history.

## 4. Conflict Resolution
- **Rule 1:** Global Knowledge is **Append-Only**. Agents cannot delete insights, only "refute" them with a newer insight.
- **Rule 2:** Local Manifests override Global Manifests. If you have a local version of a tool, the agent will use that over the Gamedrive version.
