# DOME 4.0 — Work Environment Setup Guide

> **Print this or open it on your phone.** Follow the steps in order.  
> Total time: ~10 minutes.

---

## Before You Start — What You Need

- [ ] Your work computer with admin/install access
- [ ] Git installed (check: open terminal → `git --version`)
- [ ] Python 3.10+ installed (check: `python --version`)
- [ ] Internet connection

### Credentials You'll Need (copy these now)

```
GitHub Repo:    https://github.com/Jaibesh/DOME_Shared_Brain.git
Supabase URL:   https://dvsdjfrdqftbryjtkaxk.supabase.co
Supabase Key:   sb_publishable_W7uSRzrzqjbnftvsEO7Zqw_FTMRR8eG
```

---

## Step 1: Clone the Repository (1 minute)

Open PowerShell or Terminal and run:

```powershell
git clone https://github.com/Jaibesh/DOME_Shared_Brain.git D:\DOME_CORE
```

> **If D: drive doesn't exist on your work machine**, use any path you want:
> ```powershell
> git clone https://github.com/Jaibesh/DOME_Shared_Brain.git C:\DOME_CORE
> ```
> Just remember to use that path everywhere below instead of `D:\DOME_CORE`.

### Verify it worked:
```powershell
dir D:\DOME_CORE
```
You should see: `core/`, `mcp_servers/`, `schema/`, `scripts/`, `workspaces/`, `README.md`, etc.

---

## Step 2: Create the .env File (2 minutes)

The `.env` file contains your credentials and is **never committed to Git** (it's in `.gitignore`).

```powershell
# Copy the template
Copy-Item D:\DOME_CORE\.env.template D:\DOME_CORE\.env
```

Now open `D:\DOME_CORE\.env` in any text editor and replace the contents with:

```env
# ── DOME Core ──
DOME_CORE_ROOT=D:\DOME_CORE
DOME_VERSION=4.0
DOME_ENVIRONMENT=work

# ── Supabase (Personal Account) ──
DOME_SUPABASE_URL=https://dvsdjfrdqftbryjtkaxk.supabase.co
DOME_SUPABASE_KEY=sb_publishable_W7uSRzrzqjbnftvsEO7Zqw_FTMRR8eG

# ── Agent Identity ──
AGENT_ID=work_brain
WORKSPACE_ID=D:\DOME_CORE\workspaces
```

> **IMPORTANT:** If you cloned to `C:\DOME_CORE`, change both `DOME_CORE_ROOT` and `WORKSPACE_ID` to use `C:\DOME_CORE`.

**Save and close the file.**

---

## Step 3: Install Python Dependencies (2 minutes)

```powershell
pip install supabase langgraph langgraph-checkpoint langchain-core mcp pydantic
```

> If you get permission errors, try:
> ```powershell
> pip install --user supabase langgraph langgraph-checkpoint langchain-core mcp pydantic
> ```

---

## Step 4: Run the Init Script (1 minute)

```powershell
. D:\DOME_CORE\scripts\dome_init.ps1
```

You should see output like:
```
  ╔══════════════════════════════════════════╗
  ║          DOME 4.0 — Initializing         ║
  ╚══════════════════════════════════════════╝

  [1/5] DOME_CORE located: D:\DOME_CORE
  [2/5] Git sync... ✓ Up to date
  [3/5] Loading .env... ✓ 7 variables loaded
  [4/5] Environment: WORK
  [5/5] Supabase... ✓ Connected (1 agents registered)
```

> **If Supabase says "Not configured"**: The .env file didn't load. Double-check Step 2.  
> **If Supabase says "FAILED"**: Check your internet and that the URL/key are correct.

---

## Step 5: Register Your Work Agent (1 minute)

Run this one-time registration command:

```powershell
python -c "
import sys, os
sys.path.insert(0, r'D:\DOME_CORE')

# Load env
with open(r'D:\DOME_CORE\.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

from core.supabase_client import register_agent
agent = register_agent(
    agent_id='work_brain',
    display_name='Work Brain',
    workspace_path=r'D:\DOME_CORE\workspaces',
    capabilities=['playwright_automation', 'dashboard_dev', 'tool_forging'],
    tools=['memory_client', 'supabase_client']
)
print('Agent registered:', agent.get('agent_id', 'work_brain'))
"
```

You should see: `Agent registered: work_brain`

---

## Step 6: Move Your Work Projects Into DOME (3 minutes)

This is where you bring your existing code into the synced repo.

### Dashboard:
```powershell
# Replace the path with wherever your dashboard code actually lives
xcopy /E /I "C:\path\to\your\dashboard" "D:\DOME_CORE\workspaces\dashboard"
```

### Playwright Agents:
```powershell
# Replace the path with wherever your Playwright agents live
xcopy /E /I "C:\path\to\your\playwright_agents" "D:\DOME_CORE\workspaces\playwright_agents"
```

> **Tip:** You don't have to move EVERYTHING right now. Start with whatever you're actively working on and need to refine at home tonight.

---

## Step 7: Push to Git (1 minute)

```powershell
cd D:\DOME_CORE
git add -A
git commit -m "Added work projects: dashboard + playwright agents"
git push
```

**That's it.** When you get home tonight, run:
```powershell
git -C D:\DOME_CORE pull
```
...and your work code will be there.

---

## Daily Workflow (After Setup)

### Start of day (at work):
```powershell
. D:\DOME_CORE\scripts\dome_init.ps1
```
This pulls any changes you made at home last night.

### End of day (at work):
```powershell
cd D:\DOME_CORE
git add -A
git commit -m "End of day - describe what changed"
git push
```

### At home (evening):
```powershell
git -C D:\DOME_CORE pull
# Work on your code...
git -C D:\DOME_CORE add -A
git -C D:\DOME_CORE commit -m "Fixes from home"
git -C D:\DOME_CORE push
```

---

## Optional: Set Up MCP Tools in Your IDE

If your work IDE supports MCP (Cursor, VS Code with extensions, Claude Desktop):

Add this to your MCP configuration:
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

This gives your AI assistant access to 10 DOME tools including memory search, project scaffolding, and system status.

---

## Troubleshooting

### "git is not recognized"
→ Install Git: https://git-scm.com/download/win

### "python is not recognized"
→ Install Python: https://python.org/downloads  
→ Check "Add to PATH" during install

### "pip install fails with permission error"
→ Try: `pip install --user supabase langgraph langchain-core mcp pydantic`

### "Supabase connection failed"
→ Double-check the URL and key in `.env`  
→ Make sure you have internet access  
→ Try: `python -c "import supabase; print('OK')"` to verify the package is installed

### "Git push rejected"
→ Run `git -C D:\DOME_CORE pull --rebase` first, then push again

### "The D: drive doesn't exist on my work PC"
→ Use `C:\DOME_CORE` everywhere. Update `.env` accordingly.  
→ Set environment variable: `$env:DOME_CORE_ROOT = "C:\DOME_CORE"`

---

## What's Now Shared Between Home & Work

| System | How It Syncs |
|:---|:---|
| **Code & projects** | Git push/pull |
| **Agent memory** | Supabase cloud (automatic) |
| **Insights & learnings** | Supabase cloud (automatic) |
| **Audit trail** | Supabase cloud (automatic) |
| **Workflow checkpoints** | Supabase cloud (automatic) |
| **Agent registry** | Supabase cloud (automatic) |

The **code** syncs via Git (manual push/pull).  
The **brain** syncs via Supabase (automatic — both environments read/write the same database).

---

*Generated by DOME 4.0 — 2026-04-26*
