# Directive: DOE Framework Builder

## Goal
To systematically build robust, deterministic agentic workflows using the Directive-Orchestration-Execution (DOE) framework. This framework separates high-level logic (Directives) from decision making (Orchestration) and heavy lifting (Execution).

## Core Concepts
- **Directives (Layer 1)**: Natural language SOPs (Standard Operating Procedures) in Markdown. They define the "What" and the high-level "How".
- **Orchestration (Layer 2)**: The AI Agent (e.g., in the IDE) that reads the Directive, plans the steps, and calls the tools. It handles routing and decision making.
- **Execution (Layer 3)**: Deterministic Python scripts. They handle the "How" in detail. They are atomic, reliable, and testable.
- **Context Config**: `agents.md` (or `claude.md`, `gemini.md`) provides the persistent system prompt.

## Workflow Building Process

### 1. Workspace Initialization
- Create a clear workspace folder structure.
- **Required Folders**:
    - `directives/`: Stores `.md` SOP files.
    - `execution/`: Stores `.py` scripts.
- **Recommended Folders**:
    - `.tmp/`: For scratchpad files.
    - `knowledge/` or `resources/`: For reference docs.
- **Configuration**:
    - `agents.md`: Copy the standard system prompt here.
    - `.env`: Store API keys here (never in code).

### 2. Define the Directive
- Create a new file in `directives/NAME_OF_WORKFLOW.md`.
- **Naming Convention**: Descriptive, use underscores (e.g., `scrape_leads.md`).
- **Content Structure**:
    - **Goal**: One sentence summary.
    - **Inputs**: What data is needed?
    - **Steps**: Numbered list of high-level actions.
    - **Tools**: Reference the specific Python scripts to use.
    - **Error Handling**: How to recover from failures.

### 3. Implement Execution Scripts
- For each tool mentioned in the Directive, create a corresponding script in `execution/`.
- **Principles**:
    - **Atomic**: Do one thing well (e.g., `scrape_url.py`, `send_email.py`).
    - **Deterministic**: Same input = Same output.
    - **No Logic In Code**: Avoid complex branching; leave that to the Orchestrator (Agent) unless it's pure data processing.
    - **Dependencies**: Use standard libraries or `requirements.txt`.

### 4. Orchestrate and Test
- Open the IDE Chat (The Orchestrator).
- **Inject Context**: Ensure the agent has read `agents.md`.
- **Trigger**: "Run the [Workflow Name] directive."
- **Monitor**: Watch the agent's plan. If it fails, use the error to improve the Directive or the Script.

### 5. Self-Annealing (Iterative Improvement)
- If a step is ambiguous, clarify the Directive.
- If a script fails, fix the code.
- Provide feedback to the agent to update its own instructions if necessary.
