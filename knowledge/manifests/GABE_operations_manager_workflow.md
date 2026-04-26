# Workflow: Beh Brothers Operations Manager (The "HCP Wrapper")

**Status:** ✅ LIVE (v1.0)  
**Last Updated:** 2026-01-31  
**Entry Point:** `python execution/dashboard.py` → [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## Overview

A unified interface for managing electrical business operations—from first contact to final invoice—automating paperwork before syncing with Housecall Pro.

---

## Module Architecture

```
execution/
├── dashboard.py           # Main Flask app (entry point)
├── service_upgrade_helper.py  # Legacy helper (still active)
└── modules/
    ├── __init__.py
    ├── common.py          # Shared: SMTP email, Maps links, Utility lookup
    ├── communications.py  # Smart email templates
    ├── customer.py        # CRM-lite with JSON storage
    ├── estimator.py       # Pricing engine with job templates
    └── service_upgrade.py # Service Upgrade specific logic
```

---

## Capabilities

### 1. Dashboard UI (`dashboard.py`)
- **Tabs:** Service Upgrades | Customers | Estimates
- **Styling:** Professional sidebar navigation
- **Integration:** Google Maps Autocomplete for addresses

### 2. Estimating Engine (`modules/estimator.py`)
- **Job Templates:**
  - 200A Overhead Service Upgrade
  - 200A Underground Service Upgrade
  - Recessed Lighting Installation
  - Outlet Installation
  - Electrical Troubleshooting
- **Calculation:** `(Men × Hours × Rate) + (Parts × Markup)`
- **Default Rate:** $125/man-hour
- **Default Markup:** 30% on parts

### 3. Customer Management (`modules/customer.py`)
- **Storage:** `brain/data/customers.json`
- **Fields:** ID, Name, Email, Phone, Address, Source, Notes, Jobs[]
- **ID Format:** `BEH-0001`, `BEH-0002`, etc.
- **Functions:** `create_customer()`, `get_customer()`, `search_customers()`, `add_job_to_customer()`

### 4. Communications Hub (`modules/communications.py`)
Email templates using "Welcome Sequence" best practices:

| Template | Trigger | Purpose |
|----------|---------|---------|
| `booking_confirmation` | Job scheduled | Confirm appointment details |
| `invoice` | Job completed | Send itemized bill |
| `payment_reminder` | Before due date | Friendly payment nudge |
| `review_request` | Post-job | Ask for Google/FB review |
| `retention_checkup` | 6 months later | Re-engage past customers |

### 5. Shared Utilities (`modules/common.py`)
- `determine_utility(city)` → Returns power company + phone
- `generate_google_maps_link(address)` → Maps URL
- `send_email_smtp(to, subject, body)` → Gmail SMTP sender

---

## Data Storage

| File | Purpose |
|------|---------|
| `brain/data/customers.json` | Customer profiles |
| `brain/outputs/emails/*.txt` | Saved email copies |
| `brain/outputs/hcp_jobs_import.csv` | HCP sync file |

---

## Configuration

Requires `.env` file with:
```
GMAIL_USER=your_email@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
GOOGLE_MAPS_API_KEY=AIza...
```

---

## Future Roadmap

- [ ] Direct Housecall Pro API integration (push customers/jobs)
- [ ] PDF invoice generation
- [ ] Automated follow-up scheduler (cron jobs)
- [ ] Customer search UI in dashboard
