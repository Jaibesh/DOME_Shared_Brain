# DOME Global Brain: CNS (Central Nervous System)
> Connecting isolated workspaces via the 2TB Gamedrive.

## 1. The Vision
Currently, DOME agents are limited to their local directory (their "Workspace"). The **Global Brain CNS** project transforms these isolated islands into a unified network by using the high-capacity **Gamedrive (G:\)** as a shared backbone for knowledge, tools, and memory.

## 2. Architecture Overview

### A. The Shared Backbone (`G:\DOME_CORE`)
The Gamedrive acts as the persistent storage layer that survives workspace deletions or OS reinstalls.

| Directory | Purpose | Contents |
| :--- | :--- | :--- |
| `\knowledge\` | **Shared LTM** | Global insights, agent manifests, and shared patterns. |
| `\tools\` | **Tool Library** | Reusable Python modules (`.py`) shared across all agents. |
| `\memory\` | **Global Recall** | Shared FAISS indexes for cross-workspace semantic retrieval. |
| `\registry\` | **Task Discovery** | Real-time status of which agents are running and where. |

### B. The Integration Bridge
Each workspace is "tethered" to the CNS via environment variables and refactored core modules:

1.  **DOME_CORE_ROOT**: Points to `G:\DOME_CORE`.
2.  **Global Client**: Refactored `knowledge_client.py` that dynamically switches between local and global paths.
3.  **Dynamic Tooling**: A system that imports tools directly from the CNS library.

## 3. Benefits
- **Zero-Redundancy**: Write a tool once in Workspace A, use it in Workspace Z.
- **Collective Intelligence**: When the "MLM Agent" learns a compliance rule, the "Novalee Agent" knows it instantly.
- **Persistent Memory**: Cold memory persists on the Gamedrive, enabling long-term learning over years, not just sessions.
- **Massive Scale**: Leveraging 2TB allows for millions of specialized vector embeddings and high-resolution audit logs.

## 4. Next Steps
- Refer to [GAMEDRIVE_DOME_SETUP.md](./GAMEDRIVE_DOME_SETUP.md) to initialize the drive.
- Use the [Join Global Network](../.agent/workflows/join-global-network.md) workflow to tether a new workspace.
