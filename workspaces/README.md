# DOME 4.0 — Work Projects

This directory holds active work projects that need to be accessible from both environments.

## How It Works
1. **At work:** Build/modify projects here, then `git add -A && git commit -m "..." && git push`
2. **At home:** `git pull` → your work code is here, ready to refine
3. **Push fixes from home:** `git push` → pull at work tomorrow morning

## Project Structure
```
workspaces/
├── dashboard/          # Your reservation tracking dashboard
├── playwright_agents/  # All Playwright automations
└── shared_config/      # Shared environment configs, .env templates
```

## Important
- **Never commit `.env` files** — they contain work secrets
- Use `.env.template` files to document what variables are needed
- Each project should have its own README with setup instructions
