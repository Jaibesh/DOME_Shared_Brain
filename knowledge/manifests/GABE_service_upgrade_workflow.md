# Workflow: Service Upgrade Coordination

**Goal:** Streamline the coordination of electrical service upgrades between the Client, Power Company, and our team (Alma).

> [!IMPORTANT]
> **Role:** Operations Manager Agent.
> **Trigger:** User says "Client X needs a service upgrade."

## Phase 1: Client Intake & Instructions
**Action:** When a service upgrade is requested, generate an email to the client with utility contact info.

**Step 1.1:** Identify the utility provider based on address (Monticello = Empire/City, Moab = RMP).
**Step 1.2:** Draft "Next Steps" email for the client.

**Template (Client Instructions):**
> "Hi [Client Name],
> To move forward with your service upgrade, we need you to call the power company to open a work order and schedule the disconnect/reconnect.
>
> **Who to call:**
> - **Monticello Area:** Empire Electric (800-709-3726) or City Office (435-587-2271).
> - **Moab/Other:** Rocky Mountain Power (1-888-221-7070).
>
> Once you have a date confirmed with them, please Click Here: [CALENDAR_LINK] to book us for the same time slot so we can coordinate."

---

## Phase 2: Scheduling Confirmation
**Trigger:** Client books a slot via the Calendar Link (or User manually inputs date).

**Action:**
1.  **Confirm Date:** [Date/Time]
2.  **Generate Work Packet:**
    -   **Parts List:** Standard 200A or 100A Overhead/Underground list.
    -   **Invoice:** Draft estimate/invoice for the job.
    -   **Man Hours:** Estimate labor (e.g., 2 men, 8 hours).

---

## Phase 3: Notification (Alma)
**Action:** Email Alma with the full work packet.

**Template (Email to Alma):**
> **Subject:** Scheduled Service Upgrade - [Client Name] - [Date]
>
> **When:** [Date] @ [Time]
> **Where:** [Address]
>
> **Job Scope:** [Details]
> **Man Hours:** [Est Hours]
>
> **Parts List:**
> [Insert generated parts list]
>
> The Invoice has been drafted and the client has coordinated with the utility.

## Standard Parts Lists (Templates)
*(Agent should ask user to specify Overhead vs Underground)*

**200A Overhead Service:**
- 1x 200A Meter Socket (Ringless/Horn Bypass?)
- 1x 200A Main Breaker Panel (if applicable)
- 40' 4/0 Aluminum SE Cable
- 1x 2" Rigid Mast Kit (Hub, Weatherhead, Roof Jack)
- 2x Ground Rods & Clamps
- 50' #4 Bare Copper (GEC)
- 2x Service Wedge Clamps

**200A Underground Service:**
- 1x 200A Meter Socket (Side Bus)
- 1x 2" PVC Expansion Joint
- 1x 2" Schedule 80 PVC Stick
- 2x Ground Rods & Clamps
- 50' #4 Bare Copper
## 5. Local Application (Flask)
We have built a local simulation app to handle this entire workflow.

**To Run:**
`python execution/tools/calendar_app.py`

**Features:**
- **Web Interface:** http://127.0.0.1:5000
- **Automation:** Instantly generates Email, Invoice, and Map Link on form submit.
- **Email:** Sends real emails via Gmail SMTP to the client.
- **Sync:** Logs job data to `brain/outputs/hcp_jobs_import.csv`.

## 6. Housecall Pro Integration
*(Currently Manual via CSV Import)*
- The app generates a row in `brain/outputs/hcp_jobs_import.csv`.
- **Action:** Alma imports this CSV into Housecall Pro to bulk-create the jobs.
