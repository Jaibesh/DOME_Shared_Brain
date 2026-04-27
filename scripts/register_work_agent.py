import sys, os

sys.path.insert(0, r'C:\DOME_CORE')

# Load env
with open(r'C:\DOME_CORE\.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

from core.supabase_client import register_agent
agent = register_agent(
    agent_id='work_brain',
    display_name='Work Brain',
    workspace_path=r'C:\DOME_CORE\workspaces',
    capabilities=['playwright_automation', 'dashboard_dev', 'tool_forging'],
    tools=['memory_client', 'supabase_client']
)
print('Agent registered:', agent.get('agent_id', 'work_brain'))
