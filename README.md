# DOME 4.0 — Distributed Agentic Operating System

## Overview

**DOME_CORE** is the centralized backbone for all DOME agents. It provides a cloud-native, cross-environment infrastructure for building, deploying, and managing AI agents and automations.

### Key Capabilities
- **Cloud Memory** — Supabase-backed semantic memory with pgvector (Mem0 pattern)
- **Cross-Environment Sync** — GitOps backbone syncs code between home and work
- **LangGraph Orchestration** — Stateful, cyclical agent workflows with cloud-persisted checkpoints
- **MCP Tool Servers** — 10 tools discoverable by any AI IDE (Cursor, VS Code, Claude Desktop)
- **App Factory** — Generate complete projects from templates in seconds

## Architecture

```
D:\DOME_CORE\
├── core\                       # Central Framework Logic (DOME 4.0)
│   ├── contracts.py            # Pydantic I/O contracts + graph state types
│   ├── graph_supervisor.py     # LangGraph StateGraph orchestrator
│   ├── checkpoint_saver.py     # Supabase-backed checkpoint persistence
│   ├── memory_client.py        # Mem0-pattern cloud memory (replaces knowledge_client)
│   ├── supabase_client.py      # Supabase connection manager + agent registry
│   ├── enhanced_supervisor.py  # [Legacy] DOME 2.0 supervisor (kept for reference)
│   ├── knowledge_client.py     # [Legacy] Local JSONL knowledge (superseded by memory_client)
│   ├── observability.py        # Structured logging & metrics
│   ├── policy_gate.py          # Compliance enforcement
│   └── version_tracker.py      # Component version tracking
│
├── mcp_servers\                # MCP Protocol Layer
│   ├── knowledge_server.py     # 7 tools: search/add memory, insights, agents, status
│   ├── scaffold_server.py      # 3 tools: list/scaffold/inspect templates
│   └── mcp_config.json         # IDE configuration for MCP discovery
│
├── schema\                     # Database
│   ├── supabase_schema.sql     # 6 tables + 4 functions for Supabase
│   └── rls_policies.sql        # Row Level Security policies
│
├── scripts\                    # Automation
│   └── dome_init.ps1           # Startup: git sync + env load + Supabase verify
│
├── workspaces\                 # Cross-Environment Project Sync
│   ├── dashboard\              # Work dashboard project
│   └── playwright_agents\      # Playwright automations
│
├── knowledge\                  # Local Knowledge (legacy + fallback)
│   ├── lessons\                # JSONL learning logs (local fallback)
│   ├── manifests\              # Agent design blueprints
│   └── patterns\               # Reusable SOPs and snippets
│
├── tools\                      # Shared Tool Registry
│   ├── common\                 # Shared utilities
│   └── agency\                 # Business-specific tools
│
├── .env                        # Environment credentials (gitignored)
├── .env.template               # Config template
└── .gitignore                  # Git exclusions
```

## Quick Start

### First Time Setup
```powershell
# 1. Clone the repo
git clone https://github.com/Jaibesh/DOME_Shared_Brain.git D:\DOME_CORE

# 2. Configure credentials
cp D:\DOME_CORE\.env.template D:\DOME_CORE\.env
# Edit .env with your Supabase URL and key

# 3. Install dependencies
pip install supabase langgraph mcp pydantic

# 4. Initialize
. D:\DOME_CORE\scripts\dome_init.ps1
```

### Daily Workflow
```powershell
# Start of session — sync and verify
. D:\DOME_CORE\scripts\dome_init.ps1

# End of session — push changes
git -C D:\DOME_CORE add -A
git -C D:\DOME_CORE commit -m "description of changes"
git -C D:\DOME_CORE push
```

## MCP Tool Servers

Add to your IDE's MCP settings:
```json
{
  "mcpServers": {
    "dome-knowledge": {
      "command": "python",
      "args": ["-m", "mcp_servers.knowledge_server"],
      "cwd": "D:\\DOME_CORE"
    },
    "dome-scaffold": {
      "command": "python",
      "args": ["-m", "mcp_servers.scaffold_server"],
      "cwd": "D:\\DOME_CORE"
    }
  }
}
```

### Available Tools (10 total)
| Tool | Server | Description |
|:---|:---|:---|
| `search_memory` | Knowledge | Semantic search across cloud memory |
| `add_memory` | Knowledge | Store a memory in the cloud brain |
| `search_insights` | Knowledge | Search curated insights |
| `log_insight` | Knowledge | Log a structured learning |
| `list_agents` | Knowledge | List registered DOME agents |
| `system_status` | Knowledge | System health dashboard |
| `recent_activity` | Knowledge | Audit log viewer |
| `list_templates` | Scaffold | Show available templates |
| `scaffold_project` | Scaffold | Generate a project from template |
| `inspect_template` | Scaffold | View template structure |

## DOME Tethering (for new workspaces)

Add to your workspace's `execution/__init__.py`:
```python
import sys, os
CORE_PATH = os.environ.get("DOME_CORE_ROOT", r"D:\DOME_CORE")
if os.path.exists(CORE_PATH) and CORE_PATH not in sys.path:
    sys.path.insert(0, CORE_PATH)
os.environ.setdefault("AGENT_ID", "your_agent_name")
```

## Version History

| Version | Date | Changes |
|:---|:---|:---|
| 4.0 | 2026-04-27 | Cloud-native rewrite: Supabase, LangGraph, MCP, App Factory |
| 2.2.2 | 2025-12-xx | Centralized backbone, tool registry |
| 2.0 | 2025-xx-xx | Enhanced supervisor, policy gate |
