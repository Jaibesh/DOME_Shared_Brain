# Directive: Operations & Customer Management

**Goal:** Unified interface for managing electrical business operations—from first contact to final invoice—automating paperwork before syncing with Housecall Pro.

> [!IMPORTANT]
> **Role:** Operations Manager Agent.
> **Triggers:** "New customer", "Create estimate", "Send invoice"

---

## Capability 1: Estimating Engine

### Job Templates

| Job Type | Base Hours | Men | Est. Revenue |
|----------|-----------|-----|--------------|
| 200A Overhead Service Upgrade | 8 | 2 | $2,500-3,000 |
| 200A Underground Service Upgrade | 6 | 2 | $2,000-2,500 |
| 100A Service Upgrade | 6 | 2 | $1,800-2,200 |
| Subpanel Installation | 4 | 1 | $800-1,200 |
| EV Charger (Level 2) | 4 | 1 | $800-1,200 |
| EV Charger (Long Run) | 6 | 2 | $1,200-1,800 |
| Recessed Lighting Installation | 0.5/light | 1 | $75-100/light |
| Ceiling Fan Installation | 1.5 | 1 | $200-300 |
| GFCI Outlet Installation | 1 | 1 | $150-200 |
| Dedicated 20A Circuit | 2 | 1 | $350-450 |
| Whole House Surge Protector | 1.5 | 1 | $400-500 |
| Smoke/CO Detector Install | 0.5/unit | 1 | $100-150/unit |
| Electrical Troubleshooting | 2 | 1 | $250+ |
| Panel Inspection | 1 | 1 | $125 |

### Calculation Formula
```
Total = (Men × Hours × $125) + (Parts Cost × 1.30)
```

**Default Rate:** $125/man-hour  
**Default Markup:** 30% on parts

Use `execution/estimating_engine.py` to calculate.

---

## Capability 2: Customer Management

### Customer Record Fields
| Field | Format | Example |
|-------|--------|---------|
| ID | BEH-XXXX | BEH-0001 |
| Name | String | John Doe |
| Email | String | john@example.com |
| Phone | String | 555-0101 |
| Address | String | 123 Main St, Monticello, UT |
| Source | Enum | Referral, Google, Sign, Other |
| Notes | String | Gate code 1234 |
| Jobs | Array | [] |

**Storage:** `brain/sources/customers.json`

---

## Capability 3: Communications Hub

### Email Templates

| Template | Trigger | Purpose |
|----------|---------|---------|
| `booking_confirmation` | Job scheduled | Confirm appointment details |
| `invoice` | Job completed | Send itemized bill |
| `payment_reminder` | Before due date | Friendly payment nudge |
| `review_request` | Post-job | Ask for Google/FB review |
| `retention_checkup` | 6 months later | Re-engage past customers |

Use `execution/email_utils.py` to send.

### Template: Booking Confirmation
```
Subject: Your Appointment with Beh Brothers Electric - Confirmed!

Hi [Client Name],

Your appointment has been scheduled:

📅 Date: [Date]
⏰ Time: [Time]
📍 Location: [Address]
🔧 Service: [Job Description]

What to expect:
- Our technician(s) will arrive in a marked vehicle
- Please ensure access to the electrical panel
- Estimated duration: [Hours] hours

If you need to reschedule, please call us at [Phone].

See you soon!
Beh Brothers Electric
```

### Template: Review Request
```
Subject: How did we do?

Hi [Client Name],

Thank you for choosing Beh Brothers Electric! We hope you're satisfied with our work on [Job Description].

If you have a moment, we'd really appreciate a review:
- Google: [Google Review Link]
- Facebook: [Facebook Review Link]

Your feedback helps us serve the community better.

Thanks again!
The Beh Brothers Team
```

---

## Capability 4: Housecall Pro Export

### CSV Format for HCP Import
```csv
Customer Name,Mobile Number,Email,Street Address,City,State,Zip
John Doe,555-0101,john@example.com,123 Main St,Monticello,UT,84535
```

Use `execution/utils.py` → `export_customers_csv()` to generate.

---

## Capability 5: Job Tracking

Track jobs from quote to payment with full history:

| Status | Description |
|--------|-------------|
| quote_requested | Initial inquiry received |
| quote_sent | Estimate provided to customer |
| approved | Customer accepted quote |
| scheduled | Job date/time confirmed |
| in_progress | Work underway |
| completed | Work finished |
| invoiced | Invoice sent |
| paid | Payment received |

Use `execution/job_tracker.py` → `create_job()`, `update_job_status()`, `schedule_job()`

---

## Capability 6: Reporting & Analytics

Generate business intelligence reports:

- **Weekly/Monthly Revenue** → `get_weekly_summary()`, `get_monthly_summary()`
- **Job Pipeline** → `get_jobs_by_status_summary()`
- **Outstanding Invoices** → `get_outstanding_invoices()`, `get_aging_report()`
- **Customer Analytics** → `get_customer_summary()`

Use `execution/reporting.py` for all reports.

---

## Tools Used
- `execution/estimating_engine.py` → `generate_estimate()`, `generate_invoice()`, `format_estimate_text()`
- `execution/email_utils.py` → `send_booking_confirmation()`, `send_review_request()`, `draft_email()`
- `execution/job_tracker.py` → `create_job()`, `update_job_status()`, `schedule_job()`, `get_jobs_by_status()`
- `execution/reporting.py` → `get_weekly_summary()`, `get_outstanding_invoices()`, `format_revenue_report()`
- `execution/utils.py` → `load_customers()`, `save_customer()`, `load_price_book()`, `get_part_cost()`

---

## Future Roadmap
- [ ] Direct Housecall Pro API integration (push customers/jobs)
- [ ] PDF invoice generation with company branding
- [ ] Automated follow-up scheduler (cron jobs)
- [ ] Google Calendar integration for scheduling
- [ ] SMS notifications via Twilio
- [ ] QuickBooks sync for accounting
