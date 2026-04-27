# Waiver Dashboard — System Documentation

**Version**: 2.1
**Last Updated**: April 25, 2026
**Maintainer**: Epic 4x4 Adventures Engineering

---

## 1. System Overview

The Waiver Dashboard is a real-time operations system that serves **three distinct user interfaces** from a single FastAPI backend, backed by a **Supabase PostgreSQL database** with an in-memory cache for near-instant API responses.

| Surface | URL | Audience | Purpose |
|---|---|---|---|
| **Staff Dashboard** | `/staff` | Front desk staff | Check-in, payment collection, waiver tracking, OHV permits, notes, guest details |
| **TV Arrival Board** | `/tv` `/tv/rentals` `/tv/tours` | Lobby TV screens | Live arrival queue, auto-refresh, fullscreen, no navigation chrome |
| **Customer Portal** | `/portal/{code}` | Customers (QR scan) | Pre-arrival checklist: waivers, OHV upload, countdown timer |

---

## 2. Capabilities

| Capability | Description |
|---|---|
| **Real-time Arrivals** | Fetches today's reservations from the Supabase Database, bucketed into Now/Next (0-30 min) and Upcoming (30-90+ min). Upcoming tab automatically provides 90 records to ensure proper filtered viewing on TV boards. |
| **Waiver Tracking** | Shows Epic + Polaris waiver completion as progress counts with signer names and ages |
| **OHV Permit Upload** | Customers upload OHV permits (JPG/PNG/PDF, max 10MB) via portal; staff sees completion status |
| **Check-in** | Staff marks guests as checked in with timestamp and staff name |
| **Payment Collection** | Staff records deposit collection with notes and staff attribution |
| **Overdue Detection** | Automatically flags checked-in rentals past their return time as "OVERDUE" |
| **Waiver Webhooks** | Receives live TripWorks waiver completion webhooks, extracts DOB/age/minor flag, updates counts in real-time |
| **Multi-Day Persistence** | Active multi-day rentals appear on the board until explicitly returned, even if the activity date was yesterday |
| **Customer Self-Service** | QR code links to portal where customers track waivers, OHV status, and see a countdown timer |
| **Minor Detection** | Waiver webhook calculates age from DOB and flags minors with ⚠️ in signer name list |
| **Overall Readiness** | Computes "ready" status requiring ALL: Epic OK + Polaris OK + OHV OK + Deposit collected |

---

## 3. Architecture

```
┌─────────────────────────────────────────────────┐
│           React SPA (Vite + JSX)                 │
│  ┌─────────────┐ ┌───────────┐ ┌──────────────┐ │
│  │ StaffDash   │ │ TVDash    │ │ CustomerPort │ │
│  │ DetailFly   │ │ (no nav)  │ │ OHVUploader  │ │
│  │ StatusIcon  │ │           │ │ Countdown    │ │
│  └─────────────┘ └───────────┘ └──────────────┘ │
└────────────────────┬────────────────────────────┘
                     │ HTTP API (port 8001)
┌────────────────────▼────────────────────────────┐
│            FastAPI Backend                       │
│                                                  │
│  ┌──────────────────────────────────────┐        │
│  │     In-Memory Cache                   │        │
│  │  _arrival_cache: ArrivalBoardResponse │        │
│  │  TTL: 30s | Auto-refresh: 60s        │        │
│  │  Thread lock: _cache_lock            │        │
│  └──────────────┬───────────────────────┘        │
│                 │                                 │
│  ┌──────────────▼──────────────┐                  │
│  │      supabase_data.py        │                  │
│  │  Supabase Postgres Client    │                  │
│  │  Write-through caching       │                  │
│  └─────────────────────────────┘                  │
│  ┌─────────────────────────────┐                  │
│  │     ohv_storage.py           │                  │
│  │  Local file store            │                  │
│  │  ohv_uploads/{CONF}_ohv.ext  │                  │
│  └─────────────────────────────┘                  │
│  ┌─────────────────────────────┐                  │
│  │     webhook_cache/           │                  │
│  │  Raw waiver payloads (7-day) │                  │
│  └─────────────────────────────┘                  │
└──────────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│       Supabase Database (PostgreSQL)             │
│       reservations & pending_webhooks tables     │
└──────────────────────────────────────────────────┘
```

---

## 4. File Reference

### Backend (`backend/`)

| File | Lines | Purpose |
|---|---|---|
| `main.py` | 748 | FastAPI server with all endpoints, cache logic, time bucketing, webhook handler, overdue detection |
| `supabase_data.py` | 337 | Supabase Postgres integration — read, write, mapping layer from sheet title-case to snake_case |
| `supabase_client.py`| 45  | Supabase client initialization |
| `api_models.py` | 171 | Pydantic models — ArrivalGuest (30+ fields), WaiverProgress, Portal, TV, Check-in, Payment |
| `ohv_storage.py` | 85 | OHV permit file management — save, check, validate (JPG/PNG/PDF, max 10MB) |
| `inject_dummy.py` | 292 | V2 synthetic data injector — 14 varied test reservations covering all edge cases |
| `.env` | — | Configuration (DASHBOARD_SHEET_ID, NGROK_DOMAIN, etc.) |
| `requirements.txt` | 8 | Dependencies: fastapi, uvicorn, gspread, python-dotenv, python-multipart, pytz, apscheduler |

### Frontend (`frontend/src/`)

| File | Lines | Purpose |
|---|---|---|
| `App.jsx` | 120 | React Router — StaffLayout wrapper + routes to /staff, /tv, /portal/:code |
| `components/StaffDashboard.jsx` | 16K | Main staff view — guest cards, search, filters, time buckets, action buttons |
| `components/DetailFlyout.jsx` | 19K | Slide-out panel — full guest details, check-in, payment, notes, external links |
| `components/TVDashboard.jsx` | 8K | Fullscreen lobby display — stripped navigation, auto-refresh, rental/tour filter |
| `components/CustomerPortal.jsx` | 12K | Mobile-first customer view — waiver progress, OHV upload, countdown timer |
| `components/OHVUploader.jsx` | 5K | Camera capture + file picker for OHV permit uploads |
| `components/CountdownTimer.jsx` | 3K | Live countdown to activity start time |
| `components/StatusIcon.jsx` | 2K | Reusable status badge component (ready/not_ready/check/warning) |
| `index.css` | 16K | Full design system — dark mode, glassmorphism, responsive grid, CSS variables |

---

## 5. API Endpoints

### Staff Dashboard

| Endpoint | Method | Purpose | Cache Behavior |
|---|---|---|---|
| `/api/arrivals` | GET | Today's arrivals bucketed by time | Served from cache, refreshed if stale |
| `/api/check-in/{tw_conf}` | POST | Mark checked in (timestamp + staff name) | Triggers cache refresh |
| `/api/collect-payment/{tw_conf}` | POST | Record deposit collection (staff + notes) | Triggers cache refresh |
| `/api/notes/{tw_conf}` | PATCH | Update operational notes | Triggers cache refresh |
| `/api/refresh` | POST | Force cache refresh | API key protected |

### TV Board

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/tv/rentals` | GET | Today's rentals only |
| `/api/tv/tours` | GET | Today's tours only |
| `/api/tv/all` | GET | All reservations |

### Customer Portal

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/portal/{tw_conf}` | GET | Guest status, waivers, countdown ISO timestamp |
| `/api/portal/{tw_conf}/ohv` | POST | Upload OHV permit (multipart file) |

### Webhooks

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/webhook/tw-waiver-complete` | POST | TripWorks waiver completion — updates counts + names in real-time |

### Health

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | Server status + cache age in seconds |

---

## 6. Data Model (ArrivalGuest)

The core data model tracks 35+ fields per guest:

### Identity
| Field | Type | Description |
|---|---|---|
| `tw_confirmation` | str | TripWorks confirmation code |
| `tw_order_id` | str | TripWorks order ID |
| `guest_name` | str | First + Last name |
| `primary_rider` | str | Booking holder name |

### Activity
| Field | Type | Description |
|---|---|---|
| `booking_type` | str | "Tour" or "Rental" |
| `activity_name` | str | Activity display name |
| `vehicle_model` | str | Vehicle type |
| `vehicle_qty` | int | Number of vehicles |
| `party_size` | int | Total riders |
| `activity_time` | str | Start time |
| `activity_date` | str | Activity date |

### Waivers
| Field | Type | Description |
|---|---|---|
| `epic_waivers` | WaiverProgress | Epic waiver count + signer names |
| `polaris_waivers` | WaiverProgress | Polaris waiver count + signer names |
| `WaiverProgress.completed` | int | Number completed |
| `WaiverProgress.expected` | int | Number expected |
| `WaiverProgress.names` | list[str] | Signer names with ages: "Justus Robison (25)" |

### OHV Permits (Rentals Only)
| Field | Type | Description |
|---|---|---|
| `ohv_required` | bool | True for rentals |
| `ohv_uploaded` | bool | Whether permit file exists |
| `ohv_expected` | int | Number of permits expected |
| `ohv_complete` | int | Number uploaded |
| `ohv_permit_names` | list[str] | Names of permit holders |

### Financial
| Field | Type | Description |
|---|---|---|
| `deposit_status` | str | "Due", "Collected", "Compensated" |
| `amount_due` | float | Remaining balance |
| `amount_paid` | float | Amount paid |
| `adventure_assure` | str | "None", "Free", "Premium" |

### Check-in & Rental Status
| Field | Type | Description |
|---|---|---|
| `checked_in` | bool | Whether guest is checked in |
| `checked_in_at` | str | Timestamp |
| `rental_return_time` | str | Extracted from TripWorks `experience_timeslot` webhook payload |
| `rental_status` | str | "", "On Ride", "Returned", "OVERDUE" |

### Links
| Field | Type | Description |
|---|---|---|
| `tw_link` | str | TripWorks booking URL |
| `mpwr_link` | str | MPOWR order URL |
| `mpwr_waiver_link` | str | Polaris waiver URL |
| `customer_portal_link` | str | QR code target URL |

---

## 7. Caching Strategy

### Architecture
- **Storage**: Single `_arrival_cache` variable holding an `ArrivalBoardResponse` object
- **Refresh**: APScheduler background job every 60 seconds
- **Staleness**: Each API request checks if cache is >30 seconds old
- **Thread Safety**: `threading.Lock` with double-checked locking pattern prevents concurrent refreshes

### Cache Invalidation
Every write operation triggers an immediate `_refresh_cache()`:
- Check-in → refresh
- Payment collection → refresh
- Notes update → refresh
- Waiver webhook → refresh
- Force refresh API → refresh

### Webhook Cache Cleanup
Old webhook payload files in `webhook_cache/` are automatically deleted after 7 days on startup.

---

## 8. Time Bucketing

The `_bucket_arrivals()` function sorts guests into three buckets:

| Bucket | Time Window | Description |
|---|---|---|
| `now_next` | 0-30 minutes | Guests arriving NOW or very soon |
| `upcoming` | 30-90+ minutes | Later arrivals (Buffer size: 90 to ensure TV tabs have sufficient data) |
| `checked_in` | — | Already checked in today |

### Chronological Sorting
Reservations are sorted by combining `activity_date` and `activity_time` into a unified `datetime` object. This ensures perfect chronological order across multi-day views.

### Overdue Detection
For checked-in rentals: if `rental_return_time` has passed and `rental_status` is not "Returned" or "Completed", the status is automatically set to "OVERDUE".

### Multi-Day Rental Persistence
`fetch_todays_arrivals()` includes reservations where:
- `checked_in = TRUE`
- `booking_type = "rental"`
- `rental_status != "returned"`
- Even if `activity_date` is before today

---

## 9. Webhook Handler (Waiver Completion)

### Processing Flow
1. Parse JSON body from TripWorks
2. Extract signer name and email
3. **V2: DOB Processing** — Extract date of birth, calculate age, detect minor status
4. Build display name: `"Justus Robison (25)"` or `"Minor Child (14) ⚠️MINOR"`
5. Determine waiver type from `waiver_type.name` — "polaris" → polaris, else → epic
6. Extract signed PDF URL (if present)
7. **Resolve TW Confirmation** via 3-step lookup:
   - Order ID match (preferred)
   - First+Last name match
   - Email fallback match
8. Increment waiver count + append signer name (thread-safe via `_waiver_lock`)
9. Refresh cache immediately
10. Store raw payload in `webhook_cache/` for inspection

---

## 10. OHV Permit System (ohv_storage.py)

### Storage
- **Location**: `backend/ohv_uploads/{TW_CONF}_ohv.{ext}`
- **Accepted**: `.jpg`, `.jpeg`, `.png`, `.pdf`
- **Max Size**: 10MB
- **Naming**: Confirmation code sanitized (slashes → underscores, uppercased)

### API Flow
1. Customer uploads via `/api/portal/{tw_conf}/ohv` (multipart file POST)
2. `save_ohv_permit()` validates extension + size
3. File saved to `ohv_uploads/` directory
4. Sheet updated: `OHV Uploaded = TRUE`, `OHV File Path = {path}`
5. Cache refreshed → staff dashboard updates immediately

### Existence Check
`ohv_exists()` scans all allowed extensions for `{CONF}_ohv.*` — used as fallback when Google Sheet field is empty.

---

## 11. Deposit Status Logic

`_compute_deposit_status()` determines deposit state from financial fields:

| Condition | Result |
|---|---|
| Manual override "Collected"/"Compensated" | Use override |
| Amount Due ≤ 0 AND Amount Paid > 0 | "Collected" |
| Amount Due ≤ 0 AND Amount Paid ≤ 0 AND Total > 0 | "Compensated" |
| Amount Due > 0 | "Due" |

---

## 12. Overall Readiness

A guest is "ready" when ALL conditions are met:
- `epic_complete >= epic_expected` (or no Epic waivers required)
- `pol_complete >= pol_expected` (or no Polaris required)
- `ohv_uploaded == true` (or not a rental)
- `deposit_status in ("Collected", "Compensated")`

---

## 13. Supabase Schema (Core Columns)

The Supabase `reservations` table uses snake_case column names mapped directly from the MPWR Reservation Agent. Key columns include `tw_confirmation`, `tw_order_id`, `guest_name`, `booking_type`, `activity_time`, `rental_return_time`, `epic_complete`, `polaris_complete`, `ohv_uploaded`, and `deposit_status`.


---

## 14. Frontend Design System (index.css)

### Color Palette (CSS Variables)
| Variable | Value | Usage |
|---|---|---|
| `--epic-red` | `#E31B23` | Primary brand color, CTAs |
| `--polaris-blue` | `#0073FF` | Polaris-branded elements |
| `--bg-primary` | Dark mode base | Page background |
| `--surface-card` | Elevated surfaces | Cards, flyouts |
| `--text-primary/secondary/muted` | 3-tier text hierarchy | Content visibility |

### Key Design Patterns
- **Glassmorphism**: Cards use `backdrop-filter: blur()` with semi-transparent backgrounds
- **CSS Grid**: Dashboard uses responsive grid for guest cards
- **Sidebar Layout**: Staff view has fixed sidebar + scrollable main area
- **TV Mode**: Full viewport, no scrollbars, auto-layout
- **Mobile-First Portal**: Customer portal optimized for phone screens

---

## 15. Testing (inject_dummy.py)

The dummy data injector creates 14 test reservations covering every edge case:
1. Perfect rental — fully ready, Premium AA
2. Missing OHV + 1 waiver + owes money
3. Tour missing payment + waivers (no OHV needed)
4. Checked-in ON RIDE rental
5. Checked-in RETURNED rental
6. No Adventure Assure
7. Big party (6 riders) tour — fully ready
8. Tour missing every waiver
9. Nightmare scenario — nothing completed
10. Late afternoon with minors in party (⚠️MINOR flags)
11. Checked-in tour
12. Multi-day rental — checked in yesterday, due back today
13. Tomorrow rental (should NOT appear on today's board)
14. Tomorrow tour (should NOT appear on today's board)

---

## 16. Configuration (.env)

| Variable | Purpose | Example |
|---|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | OAuth client secret | ../client_secret_2_*.json |
| `DASHBOARD_SHEET_ID` | V2 Guest Database | 1abc... |
| `NGROK_DOMAIN` | External domain for portal links | epic4x4-dashboard.ngrok.io |
| `DASHBOARD_API_KEY` | API key for force-refresh | (secret) |

---

## 17. Startup

### Backend
```
Double-click Run_Dashboard.bat
→ cd backend
→ Activates venv
→ uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

### Frontend Development
```
cd frontend
npm run dev    → Vite dev server on port 5173
```

### Frontend Production
```
cd frontend
npm run build  → Outputs to frontend/dist/
FastAPI serves dist/ via static files mount
```

---

*This document covers the Operations Dashboard as of April 16, 2026.*
