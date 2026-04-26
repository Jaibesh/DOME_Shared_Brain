# Gamedrive DOME Setup Guide
> Instructions for configuring your 2TB Gamedrive as the DOME CNS.

## 1. Physical Drive Preparation
Ensure your Gamedrive is plugged in and recognized. This guide assume the drive letter is **`G:`**.

### A. Folder Structure Creation
Run the following PowerShell command to create the necessary hierarchy:

```powershell
$root = "G:\DOME_CORE"
New-Item -ItemType Directory -Path "$root\knowledge\manifests"
New-Item -ItemType Directory -Path "$root\knowledge\lessons"
New-Item -ItemType Directory -Path "$root\knowledge\patterns"
New-Item -ItemType Directory -Path "$root\tools"
New-Item -ItemType Directory -Path "$root\memory\cold"
New-Item -ItemType Directory -Path "$root\memory\audit"
New-Item -ItemType Directory -Path "$root\registry"
```

## 2. Environment Configuration
For each workspace to recognize the CNS, you must set an environment variable.

### Option A: System-Wide (Recommended)
1. Open **Start Search**, type "Environment Variables".
2. Create a **New System Variable**:
   - **Variable Name:** `DOME_CORE_ROOT`
   - **Variable Value:** `G:\DOME_CORE`

### Option B: Local `.env` (Project Specific)
Add this line to your project's `.env` file:
```text
DOME_CORE_ROOT=G:\DOME_CORE
```

## 3. Verifying Connectivity
Once configured, you can verify if an agent can "see" the CNS by checking for the directory:

```python
import os
core_root = os.environ.get("DOME_CORE_ROOT")
if core_root and os.path.exists(core_root):
    print(f"CNS Connected at: {core_root}")
else:
    print("CNS Disconnected.")
```

## 4. Maintenance
The Gamedrive is robust, but it is recommended to back up the `G:\DOME_CORE\knowledge` folder periodically to a cloud drive (OneDrive/Google Drive) as it contains the "wisdom" of your agents.
