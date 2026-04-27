"""
DOME 4.0 — Scaffold MCP Server
================================
Exposes DOME's project scaffolding capabilities as MCP tools.

Tools Exposed:
- scaffold_project: Generate a complete project from a template
- list_templates: Show available project templates
- inspect_template: View a template's structure

Run:
    python -m mcp_servers.scaffold_server
"""

import os
import sys
import shutil
import json

DOME_ROOT = os.environ.get("DOME_CORE_ROOT", r"D:\DOME_CORE")
sys.path.insert(0, DOME_ROOT)

env_path = os.path.join(DOME_ROOT, ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "DOME Scaffold",
    instructions="DOME 4.0 Project Scaffolding — Rapidly generate new projects from battle-tested templates."
)

TEMPLATES_DIR = os.path.join(DOME_ROOT, "templates")


@mcp.tool()
def list_templates() -> str:
    """
    List all available DOME project templates.
    
    Shows template names, descriptions, and included tech stacks.
    """
    if not os.path.exists(TEMPLATES_DIR):
        return "No templates directory found. Templates will be created at D:\\DOME_CORE\\templates\\"
    
    templates = []
    for name in os.listdir(TEMPLATES_DIR):
        template_dir = os.path.join(TEMPLATES_DIR, name)
        if os.path.isdir(template_dir):
            manifest_path = os.path.join(template_dir, "manifest.json")
            if os.path.exists(manifest_path):
                with open(manifest_path) as f:
                    manifest = json.load(f)
                templates.append(f"  {name}: {manifest.get('description', 'No description')}")
                templates.append(f"    Stack: {', '.join(manifest.get('stack', []))}")
            else:
                templates.append(f"  {name}: (no manifest)")
    
    if not templates:
        return "No templates available. Use scaffold_project to create from built-in templates."
    
    return "Available Templates:\n" + "\n".join(templates)


@mcp.tool()
def scaffold_project(
    project_name: str, 
    template: str = "fullstack_saas",
    output_dir: str = "",
    description: str = ""
) -> str:
    """
    Generate a complete project from a DOME template.
    
    Creates a fully configured project directory with all boilerplate,
    pre-wired with DOME tethering, Supabase connection, and standard tooling.
    
    Args:
        project_name: Name of the new project (e.g., "my_dashboard")
        template: Template to use (fullstack_saas, playwright_agent, static_site)
        output_dir: Where to create the project. Defaults to current directory.
        description: Brief project description for README and package.json
    """
    if not output_dir:
        output_dir = os.getcwd()
    
    project_dir = os.path.join(output_dir, project_name)
    
    if os.path.exists(project_dir):
        return f"Error: Directory already exists: {project_dir}"
    
    # Check if template exists on disk
    template_dir = os.path.join(TEMPLATES_DIR, template)
    
    if os.path.exists(template_dir):
        # Copy from template
        shutil.copytree(template_dir, project_dir)
        # Run variable substitution
        _substitute_vars(project_dir, {
            "{{PROJECT_NAME}}": project_name,
            "{{DESCRIPTION}}": description or f"A DOME 4.0 {template} project",
            "{{DOME_CORE_ROOT}}": DOME_ROOT,
        })
        return f"Project scaffolded from template '{template}' at: {project_dir}"
    else:
        # Use built-in generator
        result = _generate_builtin(project_dir, project_name, template, description)
        return result


@mcp.tool()
def inspect_template(template: str = "fullstack_saas") -> str:
    """
    View the structure and contents of a project template.
    
    Args:
        template: Template name to inspect
    """
    template_dir = os.path.join(TEMPLATES_DIR, template)
    
    if not os.path.exists(template_dir):
        return f"Template '{template}' not found. Available: {', '.join(os.listdir(TEMPLATES_DIR)) if os.path.exists(TEMPLATES_DIR) else 'none'}"
    
    output = [f"Template: {template}\n"]
    for root, dirs, files in os.walk(template_dir):
        level = root.replace(template_dir, "").count(os.sep)
        indent = "  " * level
        output.append(f"{indent}{os.path.basename(root)}/")
        sub_indent = "  " * (level + 1)
        for file in files:
            filepath = os.path.join(root, file)
            size = os.path.getsize(filepath)
            output.append(f"{sub_indent}{file} ({size} bytes)")
    
    return "\n".join(output)


# =============================================================================
# BUILT-IN GENERATORS
# =============================================================================

def _substitute_vars(directory: str, variables: dict):
    """Replace template variables in all text files."""
    text_extensions = {".py", ".js", ".ts", ".tsx", ".jsx", ".md", ".json", ".yaml", ".yml", ".toml", ".sql", ".html", ".css", ".env"}
    for root, dirs, files in os.walk(directory):
        for file in files:
            if any(file.endswith(ext) for ext in text_extensions):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    for key, val in variables.items():
                        content = content.replace(key, val)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)
                except (UnicodeDecodeError, PermissionError):
                    pass


def _generate_builtin(project_dir: str, name: str, template: str, description: str) -> str:
    """Generate a project from built-in templates (no files on disk needed)."""
    
    if template == "fullstack_saas":
        return _gen_fullstack_saas(project_dir, name, description)
    elif template == "playwright_agent":
        return _gen_playwright_agent(project_dir, name, description)
    elif template == "static_site":
        return _gen_static_site(project_dir, name, description)
    else:
        return f"Unknown template: {template}. Available: fullstack_saas, playwright_agent, static_site"


def _gen_fullstack_saas(project_dir: str, name: str, desc: str) -> str:
    """Generate a FastAPI + Next.js + Supabase project."""
    dirs = [
        "backend/src/core", "backend/src/api/routes", "backend/src/services",
        "backend/tests", "backend/alembic/versions",
        "frontend/app", "frontend/components", "frontend/lib",
        "docs", "scripts"
    ]
    for d in dirs:
        os.makedirs(os.path.join(project_dir, d), exist_ok=True)
    
    # Backend entry point
    _write(project_dir, "backend/src/main.py", f'''"""
{name} — FastAPI Backend
Generated by DOME 4.0 App Factory
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="{name}", description="{desc or 'A DOME 4.0 application'}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {{"status": "healthy", "service": "{name}", "dome_version": "4.0"}}
''')
    
    # Backend config
    _write(project_dir, "backend/src/core/config.py", f'''"""Application configuration."""
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "{name}"
    database_url: str = ""
    supabase_url: str = ""
    supabase_key: str = ""
    debug: bool = True
    
    class Config:
        env_file = ".env"

settings = Settings()
''')
    
    # DOME tether
    _write(project_dir, "backend/src/__init__.py", f'''"""DOME 4.0 Tether — Connects this workspace to the centralized backbone."""
import sys, os
CORE_PATH = os.environ.get("DOME_CORE_ROOT", r"D:\\DOME_CORE")
if os.path.exists(CORE_PATH) and CORE_PATH not in sys.path:
    sys.path.insert(0, CORE_PATH)
os.environ.setdefault("AGENT_ID", "{name.lower().replace(" ", "_")}")
''')
    
    # Requirements
    _write(project_dir, "backend/requirements.txt", """fastapi>=0.111.0
uvicorn>=0.30.0
sqlalchemy[asyncio]>=2.0
alembic>=1.13
pydantic>=2.0
pydantic-settings>=2.0
supabase>=2.0
python-dotenv>=1.0
""")
    
    # Docker compose
    _write(project_dir, "docker-compose.yml", f'''version: "3.8"
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./backend:/app
    command: uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
    
  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    env_file:
      - .env
    volumes:
      - ./frontend:/app
      - /app/node_modules
    command: npm run dev
''')
    
    # .env template
    _write(project_dir, ".env.template", f"""# {name} Environment
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/{name.lower()}
DOME_SUPABASE_URL=https://your-project.supabase.co
DOME_SUPABASE_KEY=your-anon-key
DOME_CORE_ROOT=D:\\DOME_CORE
""")
    
    # README
    _write(project_dir, "README.md", f"""# {name}

{desc or 'A DOME 4.0 application.'}

## Stack
- **Backend:** FastAPI + SQLAlchemy + Supabase
- **Frontend:** Next.js (to be initialized)
- **Infrastructure:** Docker Compose
- **Framework:** DOME 4.0

## Quick Start
```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn src.main:app --reload

# Frontend
cd frontend
npm install && npm run dev
```

## DOME Tethering
This project is connected to the DOME 4.0 backbone. The backend
automatically imports shared tools and knowledge from `D:\\DOME_CORE`.

Generated by DOME 4.0 App Factory.
""")
    
    _write(project_dir, "backend/src/core/__init__.py", "")
    _write(project_dir, "backend/src/api/__init__.py", "")
    _write(project_dir, "backend/src/api/routes/__init__.py", "")
    _write(project_dir, "backend/src/services/__init__.py", "")
    
    return f"Full-stack SaaS project scaffolded at: {project_dir}\n  Backend: FastAPI + SQLAlchemy\n  Frontend: (run 'npx create-next-app@latest frontend' to initialize)\n  DOME tether: configured\n  Run: cd {name}/backend && pip install -r requirements.txt && uvicorn src.main:app --reload"


def _gen_playwright_agent(project_dir: str, name: str, desc: str) -> str:
    """Generate a Playwright automation agent project."""
    dirs = ["agents", "tools", "directives", "tests", "data"]
    for d in dirs:
        os.makedirs(os.path.join(project_dir, d), exist_ok=True)
    
    _write(project_dir, "agents/main_agent.py", f'''"""
{name} — Playwright Automation Agent
Generated by DOME 4.0 App Factory
"""
import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://example.com")
        print(f"[{name}] Page title: {{await page.title()}}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
''')
    
    _write(project_dir, "execution/__init__.py", f'''"""DOME 4.0 Tether"""
import sys, os
CORE_PATH = os.environ.get("DOME_CORE_ROOT", r"D:\\DOME_CORE")
if os.path.exists(CORE_PATH) and CORE_PATH not in sys.path:
    sys.path.insert(0, CORE_PATH)
os.environ.setdefault("AGENT_ID", "{name.lower().replace(" ", "_")}")
''')
    
    _write(project_dir, "directives/main.md", f"""# {name} Directive

## Objective
{desc or 'Automated browser workflow.'}

## Tools Available
- Playwright browser automation
- DOME cloud memory (search/store)
- DOME audit logging

## Edge Cases
- Handle login timeouts with retry
- Screenshot on failure
- Log all actions to DOME audit trail
""")
    
    _write(project_dir, "requirements.txt", """playwright>=1.40
python-dotenv>=1.0
supabase>=2.0
""")
    
    _write(project_dir, "README.md", f"""# {name}

{desc or 'A DOME 4.0 Playwright automation agent.'}

## Quick Start
```bash
pip install -r requirements.txt
playwright install chromium
python agents/main_agent.py
```

Generated by DOME 4.0 App Factory.
""")
    
    return f"Playwright agent project scaffolded at: {project_dir}\n  Agent: agents/main_agent.py\n  Directive: directives/main.md\n  DOME tether: configured"


def _gen_static_site(project_dir: str, name: str, desc: str) -> str:
    """Generate a premium static HTML/CSS/JS site."""
    dirs = ["css", "js", "assets"]
    for d in dirs:
        os.makedirs(os.path.join(project_dir, d), exist_ok=True)
    
    _write(project_dir, "index.html", f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="{desc or name}">
    <title>{name}</title>
    <link rel="stylesheet" href="css/style.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
</head>
<body>
    <header class="hero">
        <nav class="nav-container">
            <div class="logo">{name}</div>
            <div class="nav-links">
                <a href="#features">Features</a>
                <a href="#about">About</a>
                <a href="#contact" class="btn-primary">Get Started</a>
            </div>
        </nav>
        <div class="hero-content">
            <h1>{name}</h1>
            <p>{desc or 'Built with DOME 4.0'}</p>
        </div>
    </header>
    <main id="features">
        <section class="features-grid">
            <div class="feature-card">
                <h3>Fast</h3>
                <p>Built for performance from the ground up.</p>
            </div>
            <div class="feature-card">
                <h3>Modern</h3>
                <p>Cutting-edge design and technology.</p>
            </div>
            <div class="feature-card">
                <h3>Reliable</h3>
                <p>Powered by the DOME 4.0 framework.</p>
            </div>
        </section>
    </main>
    <script src="js/main.js"></script>
</body>
</html>
''')
    
    _write(project_dir, "css/style.css", '''*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
    --bg-primary: #0a0a0f;
    --bg-card: rgba(255, 255, 255, 0.04);
    --text-primary: #f0f0f5;
    --text-secondary: #8888aa;
    --accent: #6366f1;
    --accent-glow: rgba(99, 102, 241, 0.3);
    --radius: 12px;
}

body {
    font-family: "Inter", system-ui, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.6;
}

.hero {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    background: radial-gradient(ellipse at top, rgba(99,102,241,0.15), transparent 60%);
}

.nav-container {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem 3rem;
}

.logo { font-weight: 700; font-size: 1.4rem; }
.nav-links { display: flex; gap: 2rem; align-items: center; }
.nav-links a { color: var(--text-secondary); text-decoration: none; transition: color 0.2s; }
.nav-links a:hover { color: var(--text-primary); }
.btn-primary {
    background: var(--accent) !important;
    color: white !important;
    padding: 0.5rem 1.5rem;
    border-radius: 8px;
    font-weight: 500;
}

.hero-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    padding: 2rem;
}

.hero-content h1 {
    font-size: clamp(2.5rem, 6vw, 5rem);
    font-weight: 700;
    background: linear-gradient(135deg, #f0f0f5, #6366f1);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 1rem;
}

.hero-content p {
    font-size: 1.25rem;
    color: var(--text-secondary);
    max-width: 600px;
}

.features-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 1.5rem;
    padding: 4rem 3rem;
    max-width: 1200px;
    margin: 0 auto;
}

.feature-card {
    background: var(--bg-card);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: var(--radius);
    padding: 2rem;
    transition: transform 0.2s, box-shadow 0.2s;
}

.feature-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 32px var(--accent-glow);
}

.feature-card h3 {
    font-size: 1.25rem;
    margin-bottom: 0.5rem;
    color: var(--accent);
}
''')
    
    _write(project_dir, "js/main.js", '''// DOME 4.0 Static Site
console.log("DOME 4.0 — Site loaded");
''')
    
    return f"Static site scaffolded at: {project_dir}\n  Open index.html in a browser to preview."


def _write(base: str, path: str, content: str):
    """Write a file, creating directories as needed."""
    full = os.path.join(base, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    mcp.run()
