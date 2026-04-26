# DOME 2.2.2 - Centralized Backbone

## Overview

This is the **DOME_CORE** - the centralized intelligence backbone for all DOME agents. This directory serves as the single source of truth for:

- **Framework Logic** - Core modules and contracts
- **Shared Knowledge** - Unified learning across all agents
- **Tool Registry** - Reusable tools and integrations
- **Global Observability** - Centralized logging and monitoring

## Architecture

```
D:\DOME_CORE\
├── core\                       # Central Framework Logic
│   ├── contracts.py            # Global I/O Pydantic Models
│   ├── enhanced_supervisor.py  # Supervisor with runtime policies
│   ├── knowledge_client.py     # Knowledge Hub Interface
│   ├── observability.py        # Structured logging & metrics
│   ├── policy_gate.py          # Compliance enforcement
│   ├── tenant_memory.py        # Multi-tenant memory
│   ├── utils.py                # Path resolution & utilities
│   └── version_tracker.py      # Component version tracking
│
├── knowledge\                  # Shared Long-Term Memory
│   ├── manifests\              # Agent design blueprints
│   ├── lessons\                # Global learning logs (JSONL)
│   └── patterns\               # Reusable SOPs and snippets
│
├── memory\                     # Shared Vector Store
│   └── global_pine.index       # FAISS/SQLite indices
│
├── tools\                      # Unified Tool Registry
│   ├── common\                 # Shared utilities
│   │   └── migrate_knowledge.py
│   └── agency\                 # Business tools
│       ├── estimating_engine.py
│       ├── job_tracker.py
│       └── hcp_client.py
│
├── logs\                       # Global Audit Logs (NOC)
│   ├── global_audit.jsonl      # Unified audit trail
│   └── *_YYYY-MM-DD.jsonl      # Per-component logs
│
├── registry\                   # Agent Registry
│   └── agents\                 # Agent manifests
│       ├── alma_solutions.json
│       ├── gabe_bidding_solution.json
│       └── mlm_solutions.json
│
└── backups\                    # Pre-migration backups
    └── pre_2.2.2\              # DOME 2.2.1 workspace backups
```

## Key Benefits

### 1. Zero Redundancy
- Tools and knowledge are stored once and shared by all agents
- No duplicate code across agent workspaces
- Single source of truth for framework logic

### 2. Unified Observability (NOC)
- All agents log to `D:\DOME_CORE\logs\global_audit.jsonl`
- Monitor all agents from a single location
- Track costs, performance, and issues across the ecosystem

### 3. Collective Learning
- Agents share insights via the Knowledge Hub
- One agent's learning benefits all agents
- Append-only logs ensure historical knowledge is never lost

### 4. Rapid Deployment
- New agents can be deployed in ~5 minutes
- Just tether to the backbone, no need to rebuild the brain
- Consistent behavior across all agents

### 5. Cost Optimization
- Unified prompt caching reduces token usage by 40-60%
- Dynamic RAG retrieval - agents only pull what they need
- Shared tools eliminate redundant processing

## Adding a New Agent to the CNS

### Step 1: Create Workspace
```bash
mkdir "c:\Users\robis\Agentic_workflows\MyNewAgent"
cd "c:\Users\robis\Agentic_workflows\MyNewAgent"
```

### Step 2: Create Tether
Create `execution/__init__.py`:

```python
"""DOME 2.2.2 Tether"""
import sys
import os

CORE_PATH = os.environ.get("DOME_CORE_ROOT", r"D:\DOME_CORE")

if os.path.exists(CORE_PATH) and CORE_PATH not in sys.path:
    sys.path.insert(0, CORE_PATH)
    print(f"[DOME 2.2.2] Tethered to: {CORE_PATH}")

# Set agent ID
os.environ.setdefault("AGENT_ID", "my_new_agent")
os.environ.setdefault("WORKSPACE_ID", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

### Step 3: Create Agent Manifest
Create `D:\DOME_CORE\registry\agents\my_new_agent.json`:

```json
{
  "agent_id": "my_new_agent",
  "display_name": "My New Agent",
  "version": "2.2.2",
  "workspace_path": "c:\\Users\\robis\\Agentic_workflows\\MyNewAgent",
  "capabilities": ["capability1", "capability2"],
  "tools": ["tool1", "tool2"],
  "knowledge_domains": ["domain1"],
  "last_updated": "2026-02-04T16:00:00Z",
  "dome_version": "2.2.2",
  "status": "active"
}
```

### Step 4: Use Centralized Modules
In your agent code:

```python
# Import from centralized core
from core.knowledge_client import get_knowledge_client
from core.observability import create_run_tracker, create_logger
from core.contracts import Event, OutboundMessage
from core.utils import get_dome_path

# Use shared tools
from tools.agency import estimating_engine, job_tracker
```

### Step 5: Configure Environment
Create `.env`:

```env
# DOME 2.2.2 Configuration
DOME_CORE_ROOT=D:\DOME_CORE
DOME_VERSION=2.2.2
AGENT_ID=my_new_agent

# API Keys (agent-specific)
GOOGLE_API_KEY=your_key_here
```

## Knowledge Management

### Sharing Insights
```python
from core.knowledge_client import get_knowledge_client

client = get_knowledge_client("my_agent")
insight_id = client.log_insight(
    category="optimization",
    summary="Found faster way to process leads",
    content="By batching API calls, reduced processing time by 40%",
    tags=["performance", "api", "leads"]
)
```

### Searching Global Knowledge
```python
results = client.search_insights("lead processing", category="optimization")
for result in results:
    print(f"{result['summary']}: {result['content']}")
```

## Tool Development Guidelines

### Creating a New Shared Tool

1. **Place in appropriate folder**:
   - `tools/common/` for general utilities
   - `tools/agency/` for business-specific tools

2. **Use type hints and docstrings**:
```python
def my_tool(input_data: str, config: dict) -> dict:
    """
    Brief description of what the tool does.
    
    Args:
        input_data: Description
        config: Description
        
    Returns:
        Dictionary with results
    """
    # Implementation
    return {"result": "success"}
```

3. **Register in agent manifests**:
   - Update `D:\DOME_CORE\registry\agents\{agent}.json`
   - Add tool to the `tools` array

## Monitoring & Observability

### View Global Audit Logs
```powershell
# View recent entries
Get-Content "D:\DOME_CORE\logs\global_audit.jsonl" -Tail 50

# Search for specific agent
Select-String -Path "D:\DOME_CORE\logs\global_audit.jsonl" -Pattern "alma_solutions"

# Search for errors
Select-String -Path "D:\DOME_CORE\logs\global_audit.jsonl" -Pattern '"level":"ERROR"'
```

### Check Agent Registry
```powershell
# List all registered agents
Get-ChildItem "D:\DOME_CORE\registry\agents\" | Select-Object Name
```

## Backup & Recovery

### Pre-Migration Backups
All agent workspaces were backed up before the 2.2.2 migration:
- Location: `D:\DOME_CORE\backups\pre_2.2.2\`
- Includes: Full workspace copies from DOME 2.2.1

### Rollback Procedure
If needed, restore from backup:
```powershell
# Restore a specific agent
Copy-Item -Path "D:\DOME_CORE\backups\pre_2.2.2\Alma_solutions" -Destination "c:\Users\robis\Agentic_workflows\Alma_solutions" -Recurse -Force
```

## Version Information

- **DOME Version**: 2.2.2
- **Migration Date**: 2026-02-04
- **Previous Version**: 2.2.1
- **Backbone Location**: `D:\DOME_CORE`

## Support

For issues or questions:
1. Check the `FRAMEWORK_GUIDE.md` in Global_brain workspace
2. Review migration documentation in `DOME_222_MIGRATION_BLUEPRINT.md`
3. Check audit logs in `D:\DOME_CORE\logs\` for errors

---

**Status**: ✅ DOME 2.2.2 Active

