# Tech Implementation Guide: The "Systeme" Stack

> [!IMPORTANT]
> We have selected **Systeme.io** as our core infrastructure. It is free forever (up to 2,000 leads), includes email, hosting, and funnel building in one dashboard, and is the current industry standard for solopreneurs.

## 1. The Core Stack Overview
| Component | Tool Choice | Role | Cost |
| :--- | :--- | :--- | :--- |
| **All-in-One Platform** | **Systeme.io** | Funnel, Email, Blog, Affiliate tracking | **$0/mo** |
| **Video Editing** | **CapCut Desktop** | Content Creation & Editing | **$0/mo** |
| **Shorts Repurposing** | **OpusClip** | AI-chopping long video into shorts | **Freemium** |
| **Design** | **Canva** (Free) | Lead Magnets, Thumbnails | **$0/mo** |
| **Bot Automation** | **ManyChat** | Instagram DM Automation | **Freemium** |

---

## 2. Step-by-Step Setup

### Phase 1: Systeme.io Configuration
1.  **Account Creation**: Sign up for the free plan at `systeme.io`.
2.  **Domain Setup**:
    -   *Easiest*: Use the free subdomain provided (e.g., `yourname.systeme.io`).
    -   *Professional*: Buy a domain (e.g., `BiohackWith[Name].com`) via Namecheap ($10/yr) and connect it via CNAME record in Systeme settings.
3.  **Tagging Structure**:
    -   Go to **Contacts > Tags**.
    -   Create Tag: `Lead - Biohack Guide`.
    -   Create Tag: `Customer - Bought Nrf2`.
    -   Create Tag: `Biz Opp - Interested`.

### Phase 2: Building the Funnel
*Go to **Funnels > Create New > "Build an Audience"***.

#### Step A: The Squeeze Page (Opt-in)
-   **Template**: Choose a simple "E-book" template.
-   **Headline**: "The Top 5 Biohacks of 2025: Unlock Your Biology."
-   **Sub-headline**: "Discover the exact Nrf2 protocol that reduces oxidative stress by 40%."
-   **Form**: Name & Email.
-   **Button Action**: "Send Form" -> "To Next Step".
-   **Automation Rule**: Trigger: "Funnel Step Form Subscribed" -> Action: "Add Tag: [Lead - Biohack Guide]" AND "Send Email: [Email 1]".

#### Step B: The Bridge Page (Thank You)
-   **Video Embed**: Upload the "Bridge Page Video" (from Scripts Vault) directly to Systeme or YouTube (Unlisted).
-   **Text**: "Your guide is on the way! Watch this quick video while you wait."
-   **Button**: "Get the Nrf2 Synergizer Here" (Link to your LifeVantage Cart).
-   **Secondary Button**: "Join the Business Team" (Link to detailed business info).

### Phase 3: Email Automation
*Go to **Emails > Campaigns > Create "Biohack Nurture"***.

1.  **Copy/Paste**: Take the content from `email_nurture_sequence.md`.
2.  **Delays**:
    -   Email 1: 0 min delay (Immediate).
    -   Email 2: 1 Day delay.
    -   Email 3: 1 Day delay... and so on.
3.  **Activation**: Go back to your Funnel Squeeze Page -> Automation Rules -> Add Action -> "Subscribe to Campaign [Biohack Nurture]".

---

## 3. Advanced Automation (Optional but Recommended)

### ManyChat (Instagram DM Automation)
**Goal**: When someone comments "SWITCH" on your Reel, a bot sends them the link automatically.
1.  Connect Instagram to ManyChat.
2.  **New Flow**: Trigger = User comments on Post/Reel contains "SWITCH".
3.  **Action**: Send DM -> "Hey! Here is the link to the Biohack Guide: [Your Systeme.io Link]".
4.  **Why?**: This boosts algorithm engagement (comments) and ensures you never miss a lead.
