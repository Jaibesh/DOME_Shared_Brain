# Directive: Service Upgrade Coordination

**Goal:** Streamline the coordination of electrical service upgrades between the Client, Power Company, and our team (Alma).

> [!IMPORTANT]
> **Role:** Operations Manager Agent.
> **Trigger:** User says "Client X needs a service upgrade."

---

## Phase 1: Client Intake & Instructions

**Action:** When a service upgrade is requested, generate an email to the client with utility contact info.

### Step 1.1: Identify Utility Provider
- **Monticello Area:** Empire Electric or City Office
- **Moab/Other:** Rocky Mountain Power

Use the `determine_utility(city)` function from `execution/utils.py`.

### Step 1.2: Draft "Next Steps" Email

**Template (Client Instructions):**
```
Hi [Client Name],

To move forward with your service upgrade, we need you to call the power company to open a work order and schedule the disconnect/reconnect.

**Who to call:**
- **Monticello Area:** Empire Electric (800-709-3726) or City Office (435-587-2271)
- **Moab/Other:** Rocky Mountain Power (1-888-221-7070)

Once you have a date confirmed with them, please let us know so we can coordinate our crew for the same time slot.

Best regards,
Beh Brothers Electric
```

---

## Phase 2: Scheduling Confirmation

**Trigger:** Client books a slot or User manually inputs date.

**Action:**
1. **Confirm Date:** [Date/Time]
2. **Generate Work Packet:**
   - **Parts List:** Standard 200A or 100A Overhead/Underground list
   - **Invoice:** Draft estimate/invoice for the job
   - **Man Hours:** Estimate labor (e.g., 2 men, 8 hours)

Use `execution/estimating_engine.py` to generate the work packet.

---

## Phase 3: Notification (Alma)

**Action:** Email Alma with the full work packet.

**Template (Email to Alma):**
```
Subject: Scheduled Service Upgrade - [Client Name] - [Date]

When: [Date] @ [Time]
Where: [Address]

Job Scope: [Details]
Man Hours: [Est Hours]

Parts List:
[Insert generated parts list]

The Invoice has been drafted and the client has coordinated with the utility.
```

---

## Standard Parts Lists

> [!TIP]
> Ask user to specify **Overhead** vs **Underground** type.

### 200A Overhead Service
| Item | Qty | Notes |
|------|-----|-------|
| 200A Meter Socket | 1 | Ringless/Horn Bypass |
| 200A Main Breaker Panel | 1 | If applicable |
| 4/0 Aluminum SE Cable | 40' | |
| 2" Rigid Mast Kit | 1 | Hub, Weatherhead, Roof Jack |
| Ground Rods & Clamps | 2 | |
| #4 Bare Copper (GEC) | 50' | |
| Service Wedge Clamps | 2 | |

### 200A Underground Service
| Item | Qty | Notes |
|------|-----|-------|
| 200A Meter Socket (Side Bus) | 1 | |
| 2" PVC Expansion Joint | 1 | |
| 2" Schedule 80 PVC Stick | 1 | |
| Ground Rods & Clamps | 2 | |
| #4 Bare Copper | 50' | |

---

## Tools Used
- `execution/utils.py` → `determine_utility(city)`
- `execution/estimating_engine.py` → `generate_estimate()`, `generate_parts_list()`
- `execution/email_utils.py` → `send_email_smtp()`

---

## Edge Cases
- **Unknown City:** Ask user to confirm utility provider
- **Custom Parts:** Add to `brain/sources/price_book.csv` and recalculate
- **Rush Job:** Note expedited timeline in work packet
