# Epic 4x4 Waiver Reconciliation System - SOP

## Mission Goal
This system pulls customer data from **Tripworks** and cross-references it dynamically with signed liability releases in **Polaris MPOWR**. The reconciliation pipeline guarantees that every participant has successfully completely both required waiver formats, syncing the structured output continuously to a Google Sheet database.

## System Interfaces
- **Google Sheets OAuth**: Natively handled leveraging `#do_auth.py` and stored sequentially in `backend/authorized_user.json`. The agent scopes manipulate the `1ty4SLvT8KA9S8SVzxoaVbELA48KwiT2uFoE1rsSQ1UY` spreadsheet strictly tied to the `justus@epic4x4adventures.com` identity.
- **Frontend Architecture**: Compiled exclusively via `Vite` (React) targeting `Plus Jakarta Sans` typography. 
- **Active Scrapers**: Handled by python background scheduling via `main.py` executing hourly blocks.

## Development Constraints
1. Modifying scraping headers must be matched heavily by try-except blocks ensuring `CANCELED` timeouts don't crash the Uvicorn engine natively.
2. The UI structure mandates strict isolation between the Admin layout, the Customer search queries, and the completely detached `/tv` Full-Screen interface intended for physical office displays.
3. Only write API changes referencing **Pydantic Models** mapped in `api_models.py`.
