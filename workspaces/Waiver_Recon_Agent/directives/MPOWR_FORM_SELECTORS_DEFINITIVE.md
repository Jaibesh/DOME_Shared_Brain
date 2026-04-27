# MPOWR Form Selectors — Definitive Reference

> **LAST UPDATED: April 10, 2026 — After 5 rounds of live MPOWR testing**
> **STATUS: VERIFIED ✅ — All selectors confirmed working against live MPOWR**

This document is the single source of truth for all MPOWR UI interactions.
Any code that interacts with the MPOWR form MUST use these selectors.

---

## 1. Login

| Field | Selector | Notes |
|-------|----------|-------|
| Email | `input[name='email']` | Standard |
| Password | `input[name='password']` | Standard |
| Submit | `button[type='submit']` | — |

---

## 2. Choose Listing Modal

**CRITICAL: MPOWR uses a VIRTUALIZED LIST** — only ~8 of 10 listings are
rendered in the DOM at any time. Must scroll to render hidden items.

| Element | Selector | Notes |
|---------|----------|-------|
| Open modal | `button` with text matching listing name or "Choose Listing" | First match |
| Radio group | `[role='radiogroup']` | Contains listing cards |
| Individual card | `[role='radio']` with `has_text=<name>` | May need scroll |
| Scrollable container | `div.fixed.inset-0.z-10.overflow-y-auto` | Scroll this, not radiogroup |

**Scrolling strategy:**
```python
scroll_container = page.locator("div.fixed.inset-0.z-10.overflow-y-auto").first
for attempt in range(6):
    card = page.locator("[role='radio']").filter(has_text=target).first
    if card.count() > 0:
        card.scroll_into_view_if_needed()
        card.click()
        break
    scroll_container.evaluate("el => el.scrollBy(0, 400)")
    time.sleep(0.5)
```

**Apostrophe handling:** Hell's Revenge uses curly right single quote `'` (U+2019).
Always try both straight `'` and curly `'` variants.

### All Listings (as of April 2026)
1. 24 Hour Rental
2. 3 Hour Self-Guided Adventure Rental-Moab's Scenic Wonders Awaits
3. Multi-Day Adventure Rental
4. Poison Spider Mesa
5. Full-Day Adventure – Explore Moab's Best with Custom Curated Routes
6. Half-Day Slingshot
7. Half-Day Self-Guided Rental – Custom Routes to Match Your Spirit of Exploration
8. Full Day of Scenic Moab in a Slingshot R
9. Hell's Revenge ← REQUIRES SCROLL (bottom of list)
10. Moab Discovery Tour ← REQUIRES SCROLL (bottom of list)

---

## 3. Date Picker

| Element | Selector | Notes |
|---------|----------|-------|
| Date input | `input[placeholder='MM / DD / YYYY']` | Click to open calendar |
| Month navigation | `button[aria-label='Go to previous month']` / `button[aria-label='Go to next month']` | — |
| Day cells | `button.rdp-day_button` matching day number | Don't click disabled (already-past) days |

**Strategy:** Triple-click to select all text in the date input, then type the date.
```python
date_input.click(click_count=3)
date_input.type("04/15/2026")
```

---

## 4. Time Picker (Headless UI Listbox)

**NOT a native `<select>`** — uses a custom Headless UI Listbox component.

| Element | Selector | Notes |
|---------|----------|-------|
| Trigger button | `button[aria-haspopup='listbox']` OR near "Start Time" label | Click to open |
| Options container | `[role='listbox']` | Modal with options |
| Individual option | `[role='option']` | Click matching text |

**Time format normalization** — MPOWR shows times like `9am`, `2pm`, `8:30 am`.
Must normalize input from various formats:
- `"9:00 AM"` → `"9am"`
- `"10 AM"` → `"10am"`  
- `"0.375"` (decimal) → `"9am"`
- `"9:00:00 AM"` → `"9am"`
- `"17:00"` (24h) → `"5pm"`

---

## 5. Vehicle Selection

| Element | Selector | Notes |
|---------|----------|-------|
| Vehicle text | `get_by_text(name, exact=True)` | **MUST use exact=True** |
| Card wrapper | `div` filtered by has=text AND has=`select` | Use `.last` for deepest |
| Qty dropdown | `card.locator("select").first` | Native `<select>`, use `select_option(value=qty)` |

**CRITICAL: "RZR PRO S" vs "RZR PRO S4"**
Using `exact=False` causes "RZR PRO S" to match "RZR PRO S4".
Always use `exact=True` first, fallback to regex word boundary.

### Vehicle Cards Available Per Listing
| Listing | Vehicles |
|---------|----------|
| Hell's Revenge | RZR Pro R, RZR PRO S, RZR PRO S4, RZR XP4 S |
| Poison Spider Mesa | RZR Pro R only |
| Moab Discovery Tour | XPEDITION XP 5 NorthStar |
| 3 Hour / Half-Day / Full-Day Rental | RZR Pro R, RZR PRO S, RZR PRO S4, RZR XP S, RZR XP4 S |
| 24 Hour Rental | RZR Pro R, RZR PRO S, RZR PRO S4, RZR XP S, RZR XP4 S |

---

## 6. AdventureAssure Insurance Modal

| Element | Selector | Notes |
|---------|----------|-------|
| Trigger | `get_by_text("Choose AdventureAssure")` | Opens modal |
| Standard option | `get_by_text("AdventureAssure Standard Protection")` | Free |
| Upgraded option | `get_by_text("AdventureAssure Upgraded Protection")` | $118 |
| Close | `Escape` key | Dismiss modal |

**WARNING:** This modal also triggers automatically when:
- Vehicle quantity changes
- Rental add-ons are added via the "Add" button

Always press `Escape` after any action that may trigger this modal.

---

## 7. Additional Questions (Checkboxes)

| Element | Selector | Notes |
|---------|----------|-------|
| Checkboxes | `input[type='checkbox']` | Uncheck SMS consent, check rest |
| Filter | Skip if `id` contains "consent" or label contains "SMS" | Don't check SMS opt-in |

**Activities with checkboxes:** All rentals (3hr, Half-Day, Full-Day, 24hr, Multi-Day)
**Activities without checkboxes:** All tours (Hell's Revenge, Poison Spider, Moab Discovery)

### Checkbox list (rentals):
1. ✅ Driver minimum age requirement: 25 years of age or older
2. ✅ MANDATORY UTAH OHV VEHICLE EDUCATION COURSE
3. ✅ I acknowledge that reckless driving...

---

## 8. Guide Add-Ons

| Element | Selector | Notes |
|---------|----------|-------|
| Section header | `get_by_text("Rental Add-Ons")` | Scroll into view first |
| Search input | `input[placeholder*='find rental add-ons']` | Type guide name |
| Add button | `button` with text "Add" | In search result card |
| Increment (+) | Button "+" in guide card | For qty > 1 |

**Auto-included guides** (Min. 1 per order, no search needed):
- Poison Spider Mesa → "Poison Spider Guide Services" ($257)
- Moab Discovery Tour → "Moab Discovery Tour Guide Services" (price varies)

**Search-required guides:**
- Hell's Revenge → "Gateway Party of 1-2 - Guide Services" ($159)
- Hell's Revenge → "Gateway Party of 3-4 - Guide Services" ($229)

---

## 9. Customer Info

Located at the BOTTOM of the form. Scroll to `document.body.scrollHeight` first.

| Field | Selector | Notes |
|-------|----------|-------|
| First Name | `get_by_role("textbox", name="First Name", exact=True)` | **NOT** get_by_label |
| Last Name | `get_by_role("textbox", name="Last Name", exact=True)` | **NOT** get_by_label |
| Email | `get_by_role("textbox", name="Email", exact=True)` | **NOT** get_by_label (collides with OHV checkbox) |
| Phone | `get_by_role("textbox", name="Phone", exact=True)` | **NOT** input[name='customer.phone'] |

**Why `get_by_role` instead of `get_by_label` or `input[name=...]`:**
- `get_by_label("Email")` matches BOTH the email text input AND the OHV course checkbox label → Playwright strict-mode violation
- `input[name='customer.phone']` → field's actual `name` attribute is different (possibly `customer.phoneNumber`)
- `get_by_role("textbox", name="...", exact=True)` only matches `<input>` elements with matching accessible name — never checkboxes

---

## 10. Submit / DRY_RUN

| Element | Selector | Notes |
|---------|----------|-------|
| Reserve Now button | `button` with text "Reserve Now" | Only click if DRY_RUN=false |
| Pre-submit screenshot | Full page screenshot | Always capture before submit |
