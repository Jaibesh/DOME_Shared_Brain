# Agent System Context

## Workspace Organization
This workspace follows the **DOE (Directive-Orchestration-Execution) Framework**:

- **Directives** (`directives/`): Natural language SOPs and workflow definitions
- **Orchestration**: You (the AI agent) read directives, plan steps, and call tools
- **Execution** (`execution/`): Deterministic Python scripts for heavy lifting
- **Modules** (`modules/`): Organized Python packages for shared functionality
- **Tools** (`tools/`): Specialized utility scripts
- **Knowledge** (`knowledge/`): Reference documentation and guides
- **Legacy** (`legacy/`): Archived/deprecated code

## Core Principles

1. **Separation of Concerns**: Keep decision logic (orchestration) separate from execution code
2. **Atomic Operations**: Each script does one thing well
3. **Deterministic**: Same input = same output
4. **Documented**: Every directive explains the "what" and "why"

## How to Work With This System

### Running a Workflow
1. Read the directive from `directives/[workflow_name].md`
2. Understand the goal, inputs, and steps
3. Execute the workflow by calling scripts from `execution/` or `tools/`
4. Handle errors according to the directive's error handling section

### Creating New Workflows
1. Define the directive in `directives/` first
2. Implement required execution scripts in `execution/`
3. Test the workflow end-to-end
4. Document any learnings or edge cases

### Key Projects in This Workspace

- **Gabe's Dirtwork Bidding Tool**: Construction estimation and bidding system
- **Agent Supervisor**: Multi-agent orchestration system
- **Knowledge Hub**: Tenant-specific memory and knowledge management
- **Service Upgrade Workflows**: Customer lifecycle management
- **Database Migration**: Phase 5 Complete (PostgreSQL integration)

## Environment

- Store API keys and secrets in `.env` (never commit)
- Use `modules/` for shared functionality across workflows
- Use `.tmp/` for temporary/scratch files

## Reference Documentation

All reference docs are in `knowledge/`:
- DOE Framework Builder guide
- Gabe Bidding Tool specifications
- Productivity references
- Cross-workspace sync guides
