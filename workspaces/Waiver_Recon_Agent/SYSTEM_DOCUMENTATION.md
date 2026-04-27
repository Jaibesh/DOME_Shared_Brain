# Waiver Recon Agent — System Documentation

**Version**: 2.0
**Last Updated**: April 16, 2026
**Maintainer**: Epic 4x4 Adventures Engineering

---

## 1. System Overview

The Waiver Recon Agent is an automated reconciliation system that cross-references waiver completion status between **MPOWR** (Polaris waivers) and **TripWorks** (Epic waivers). It scrapes MPOWR rider data using Playwright, matches riders to TripWorks records via fuzzy name matching, identifies missing waivers, triggers automated reminder emails, and syncs everything to Google Sheets.

The system operates within the **DOME 2.2.2 Architecture** (Directive/Orchestration/Memory/Execution), a 4-layer framework that separates intent from action.

---

## 2. Capabilities

| Capability | Description |
|---|---|
| **MPOWR Scraping** | Playwright scrapes each MPOWR reservation page to extract rider names, emails, phones, child status, and waiver status |
| **TripWorks Waiver Lookup** | Cross-references riders against TripWorks waiver records via API |
| **Fuzzy Name Matching** | Uses `thefuzz.fuzz.token_sort_ratio` with 75% threshold for cross-platform rider matching |
| **Webhook Email Detection** | Identifies and flags auto-generated `polaris+CONF@epic4x4adventures.com` emails for cleanup |
| **Email Reminders** | Sends HTML reminder emails to customers with links to both waiver portals |
| **Staff Failure Alerts** | Sends urgent staff emails when automated MPOWR creation fails |
| **Google Sheets Sync** | Batch-writes reconciled waiver counts back to the tracking sheet |
| **Secondary Sheet Tracking** | Maintains a separate sheet tracking which TW Confirmations have been processed |
| **REST API** | FastAPI dashboard for manual status checks, sync triggers, and customer search |
| **Slack Notifications** | Rich Block Kit messages for every reservation outcome (success, error, duplicate, dry run) |
| **Screenshot Forensics** | Captures and uploads pre-submit screenshots for every creation attempt |
| **Retry System** | Failed rows marked `RETRY_N` are re-attempted up to 3 times |

---

## 3. Architecture

## 3. Architecture

```
                                         ┌──► Supabase `reservations` Table (Source of Truth)
                                         │       ▲
TripWorks Webhooks ─────► Cloud Gateway ─┘       │ (Writes waiver counts & minor flags)
                                                 │
MPOWR (Playwright) ◄──── scraper.py ─────────────┘
                          (Runs hourly via main.py daemon)
```

### DOME 2.2.2 Architecture Integration
- **Directives** (`directives/`): SOPs, branding guide, MPOWR form selectors reference, patch history
- **Orchestration**: Lightweight APScheduler hourly cron (main.py)
- **Execution** (`execution/`): Tool registry tethered to `D:\DOME_CORE` centralized framework

---

## 4. File Reference

### Backend (`backend/`)

| File | Lines | Purpose |
|---|---|---|
| `main.py` | 75 | Lightweight APScheduler daemon that triggers the scraper hourly |
| `scraper.py` | 150 | MPOWR scraper — queries Supabase, navigates to each reservation, extracts Polaris riders |
| `mpowr_browser.py` | 65 | Centralized Playwright login flow handling the MPOWR Pre-SSO Gateway |
| `waiver_link_storage.py` | 130 | Supabase connection logic (shared with other agents) |
| `slack_notifier.py` | 450 | Slack Block Kit notifications — sends summary metrics at the end of each run |
| `waiver_webhook_daemon.py` | 250 | Polling script for `recon_webhooks` queue, self-healing framework, demographic extraction |
| `requirements.txt` | 14 | Dependencies: playwright, fastapi, slack-sdk, supabase, etc. |

### Directives (`directives/`)

| File | Purpose |
|---|---|
| `WAIVER_RECONCILIATION_SOP.md` | Mission goal, system interfaces, development constraints |
| `MPOWR_FORM_SELECTORS_DEFINITIVE.md` | **Critical reference** — every Playwright selector for MPOWR forms (login, listing modal, date picker, time picker, vehicle selection, insurance, customer info, submit) |
| `BRANDING_GUIDE.md` | Epic 4x4 brand colors (Candy Red `#E81B1B`, Black `#181818`, White) + typography (Plus Jakarta Sans) |
| `PATCH_HISTORY.md` | 5 documented patches: cache pre-warming, scraper error boundary, header anomaly handling, name normalization, React sync state |
| `TV_DASHBOARD_WALKTHROUGH.md` | TV Board architecture: stripped nav, fractional waiver math, date filtering |
| `GLOBAL_BRAIN_ARCHIVE_PLAN.md` | Token optimization and subscription consolidation plan |

### Additional Files

| File | Purpose |
|---|---|
| `fetch.py` | One-off utility — scrapes Epic 4x4 website for the logo image |
| `execution/__init__.py` | DOME tether — adds `D:\DOME_CORE` to sys.path, sets `AGENT_ID=epic_4x4_waiver_recon` |
| `brain/` | Empty directory — reserved for LangGraph checkpoint persistence |

---

## 5. Reconciliation Logic (scheduled_job)

### Step-by-Step Flow
1. **Time Guard**: Only runs between 6 AM and 10 PM Mountain Time
2. **MPOWR Scrape**: Login via `mpowr_login.py`, navigate to `/orders`, visit each reservation page
3. **Rider Extraction**: Parse rider rows looking for "Completed Waiver" or "Missing Waiver" text
4. **TripWorks Fetch**: Call TripWorks API for waiver status records
5. **Reconciliation Loop**: For each MPOWR rider:
   - Try exact email match (case-insensitive) → 100% confidence
   - Fallback to fuzzy name match → 75%+ threshold
6. **Webhook Email Handling**: Detect `polaris+CONF@epic4x4adventures.com` patterns
   - Has waiver + no duplicate name → keep normally
   - Otherwise → flag `needs_deletion: true`
7. **Cache in Memory**: Store reconciled data in `dashboard_cache` dict
8. **Google Sheets Sync**: Batch update Polaris/Epic waiver counts
9. **Email Dispatch**: Send HTML reminder to primary email if any riders missing waivers

### Pre-Warming
On startup, `main.py` primes the cache from Google Sheets via `fetch_database()` so the dashboard isn't empty before the first hourly sync.

---

## 6. Fuzzy Matching Engine

### Name Normalization (`normalize_name`)
```
Input:  "Jean-Daniel M Sabourin"
Step 1: lowercase → "jean-daniel m sabourin"
Step 2: strip special chars → "jeandaniel m sabourin"
Step 3: remove single-letter words → "jeandaniel sabourin"
Output: "jeandaniel sabourin"
```

### Match Priority
| Priority | Method | Confidence | Threshold |
|---|---|---|---|
| 1st | Exact email match | 100% | — |
| 2nd | Fuzzy name (`token_sort_ratio`) | Variable | ≥ 75% |
| — | Below threshold | 0% | → "Missing Waiver" |

### Webhook Email Rules
- **Pattern**: `polaris+{CONF}@epic4x4adventures.com`
- **If rider has completed waiver AND no duplicate name** → keep, `needs_deletion: false`
- **Otherwise** → keep but flag `needs_deletion: true` for front desk cleanup

---

## 7. Scraper Details (scraper.py)

### MPOWR Reservation Page Parsing
- Lists all `/orders/{id}` links from the MPOWR orders page
- For each reservation URL:
  - Extracts `reservation_id` from URL path
  - Locates rider rows by searching for `div:has-text('Riders')` parent containers
  - Parses `Completed Waiver` / `Missing Waiver` from row text content
  - Extracts emails via regex: `[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+`
  - Extracts phones via regex: `\d{3}-\d{3}-\d{4}`
  - Detects child riders via "child" or "minor" in HTML content
  - Parses waiver count from format: `"Jean-Daniel Sabourin - 4"` → name + count

### Virtualized List Handling
MPOWR uses a virtualized list that renders only ~8 items at a time. The scraper handles this with scroll-based rendering (documented in `MPOWR_FORM_SELECTORS_DEFINITIVE.md`).

---

## 8. Google Sheets Integration (sheets.py)

### Two Sheets

| Sheet | Purpose | Key Functions |
|---|---|---|
| **Primary (GOOGLE_SHEET_ID)** | Zapier-fed reservation data | `fetch_database()`, `sync_to_google_sheets()`, `scan_for_pending_creations()` |
| **Secondary (SECONDARY_SHEET_ID)** | Creator bot tracking | `log_secondary_state()`, processed TW Confirmations |

### Production Safeguards
- **BUG-2**: Max 20 rows per scheduler cycle (`MAX_PER_RUN = 20`)
- **EDGE-9**: Past-date rows auto-filtered during scanning
- **BUG-6**: `batch_write_results()` uses single API call (avoids 300 req/min quota)
- **ARCH-1**: `mark_for_retry()` writes `RETRY_N: {error}` for re-attempts (max 3)
- **PERF-2**: `load_dotenv()` called once at module import level
- **EDGE-4**: `insert_row(index=2)` bypasses active Google Sheets filters
- **Backoff**: `execute_with_backoff()` with exponential retry on 429 errors

### Creation Lock System
- `set_creation_lock()`: Atomically writes status to MPWR Confirmation column
- Prevents duplicate processing during concurrent runs

---

## 9. Email System (mailer.py)

### Customer Waiver Reminder
- **Triggered**: When any rider in a reservation has an incomplete waiver
- **Recipients**: Primary email on the reservation (one email per reservation)
- **Content**: HTML email listing missing riders with links to both MPOWR and TripWorks waiver portals
- **Transport**: SendGrid SMTP (configurable)

### Staff Creation Alert
- **Triggered**: When automated MPOWR creation fails
- **Recipients**: `STAFF_ALERT_EMAIL` env var (default: `justus@epic4x4adventures.com`)
- **Content**: Customer name, TW Confirmation, activity date, vehicle type, error reason + manual creation link
- **Subject**: "⚠️ URGENT: Manual MPOWR Creation Required — {customer_name}"

---

## 10. Slack Notifications (slack_notifier.py)

### Notification Types
| Icon | Type | Method |
|---|---|---|
| ✅ | Reservation Created | `send_reservation_success()` |
| ❌ | Creation Failed | `send_error_alert()` |
| ⚠️ | Duplicate Detected | `send_duplicate_alert()` |
| 🧪 | Dry Run Complete | `send_dry_run_alert()` |
| 💰 | Price Override | `send_price_override_alert()` |
| 📊 | Batch Summary | `send_success_summary()` |

### Message Dispatch Priority
1. **Bot Token DM** (supports file uploads for screenshots)
2. **Incoming Webhook** (no file upload, text/blocks only)
3. **Console fallback** (when both are unconfigured)

### Screenshot Upload
Uses Slack's `files.upload` API to attach pre-submit screenshots to DM messages.

---

## 11. Data Models (api_models.py)

### Rider
| Field | Type | Description |
|---|---|---|
| `name` | str | Full rider name |
| `is_child` | bool | Whether rider is a minor |
| `email` | Optional[str] | Rider email |
| `phone` | Optional[str] | Rider phone |
| `mpowr_status` | str | "Completed Waiver" or "Missing Waiver" |
| `tripworks_status` | str | "Completed Waiver" or "Missing Waiver" |
| `needs_deletion` | bool | Flag for webhook email cleanup |

### CustomerPayload (Creator Bot Input)
| Field | Type | Description |
|---|---|---|
| `first_name` / `last_name` | str | Customer name |
| `webhook_email` | str | polaris+{TW_Conf}@epic4x4adventures.com |
| `tw_confirmation` | str | TripWorks confirmation code |
| `booking_type` | str | "tour" or "rental" |
| `mpowr_activity` | str | Mapped MPOWR listing name |
| `mpowr_vehicle` | str | Mapped MPOWR vehicle card text |
| `vehicle_qty` | int | Number of vehicles |
| `target_price` | float | TripWorks sub-total for price override |

---

## 12. API Endpoints

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/api/health` | GET | None | System status + cache size + timestamp |
| `/api/dashboard` | GET | None | Full reconciled dashboard data (all reservations) |
| `/api/trigger_sync` | POST | API Key | Manually trigger a reconciliation run |
| `/api/customer/status?query=` | GET | None | Search by TW Confirmation or rider name |

### Frontend (Legacy)
- `/assets/` — Mounted Vite static files
- `/{full_path:path}` — SPA catch-all serving React `index.html`

---

## 13. MPOWR Form Selectors Reference

The `MPOWR_FORM_SELECTORS_DEFINITIVE.md` directive documents every Playwright selector used across the system. Key sections:

| Section | Selector Strategy | Gotgas |
|---|---|---|
| Login | `input[name='email/password']` | Standard |
| Listing Modal | `[role='radio']` with scroll | Virtualized list — only ~8 items visible |
| Date Picker | `input[placeholder='MM / DD / YYYY']` | Triple-click to select, then type |
| Time Picker | `button[aria-haspopup='listbox']` | NOT native `<select>` — custom Headless UI |
| Vehicles | `get_by_text(name, exact=True)` | MUST use exact=True ("RZR PRO S" vs "RZR PRO S4") |
| Insurance | `get_by_text("Choose AdventureAssure")` | Modal auto-triggers on vehicle change |
| Customer Info | `get_by_role("textbox", name=..., exact=True)` | NOT get_by_label (collides with checkbox) |
| Submit | `button` with text "Reserve Now" | DRY_RUN check before click |

### Apostrophe Handling
Hell's Revenge uses curly right single quote `'` (U+2019). Code must try both straight `'` and curly `'`.

---

## 14. Configuration (.env)

| Variable | Purpose | Example |
|---|---|---|
| `MPOWR_EMAIL` | MPOWR login email | user@epic4x4adventures.com |
| `MPOWR_PASSWORD` | MPOWR login password | ••••• |
| `GOOGLE_APPLICATION_CREDENTIALS` | Google OAuth client secret JSON path | ./client_secret.json |
| `GOOGLE_SHEET_ID` | Primary waiver tracking sheet | 1ty4SLvT8... |
| `SECONDARY_SHEET_ID` | Bot confirmation tracker | (different ID) |
| `SMTP_SERVER` | Email server | smtp.sendgrid.net |
| `SMTP_PORT` | Email port | 587 |
| `SMTP_USER` | Email username | apikey |
| `SMTP_PASS` | Email password / API key | SG.••••• |
| `FROM_EMAIL` | Sender address | info@epic4x4adventures.com |
| `STAFF_ALERT_EMAIL` | Staff alert recipient | justus@epic4x4adventures.com |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook URL | https://hooks.slack.com/... |
| `SLACK_BOT_TOKEN` | Slack bot token | xoxb-••••• |
| `SLACK_USER_ID` | Slack user ID for DMs | U0123456789 |
| `CREATOR_API_KEY` | API key for protected endpoints | (secret) |
| `START_ROW` | Row to start scanning from | 2 |
| `DRY_RUN` | Fill forms but don't submit | true/false |
| `TRIPWORKS_API_KEY` | TripWorks API auth key | (from TW dashboard) |

---

## 15. Dependencies

```
playwright, gspread, google-auth, google-auth-oauthlib, google-auth-httplib2,
requests, python-dotenv, apscheduler, fastapi, uvicorn, thefuzz, pydantic,
slack-sdk, pytest
```

---

## 16. Startup

**1. Run_Live_Bot.bat (Recon Engine + Backend API)**
1. `cd backend`
2. Creates or activates Python virtual environment
3. Installs dependencies + Playwright Chromium (first run only)
4. Launches `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
5. Scheduler starts hourly reconciliation (on the hour mark)

**2. Run_Webhook_Daemon.bat (Self-Healing Webhook Processor)**
1. Activates Python virtual environment
2. Launches `waiver_webhook_daemon.py`
3. Infinitely polls Supabase `recon_webhooks` queue every 60 seconds

**3. Run_Waiver_Link_Scraper.bat (MPOWR Link Scraper)**
1. Launches `waiver_link_daemon.py`
2. Infinitely polls Supabase for missing links and scrapes them from MPOWR

---

*This document covers the Waiver Recon Agent as of April 24, 2026.*
