# 04 — Parts Ordering & Polaris Portal Integration

## Parts Ordering Workflow Overview

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  AI Generates │────▶│  Mechanic    │────▶│  Portal Agent│────▶│  Order       │
│  Parts List   │     │  Reviews &   │     │  Submits to  │     │  Confirmed   │
│               │     │  Approves    │     │  Polaris     │     │  & Tracked   │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

---

## Polaris Dealer Portal Automation

### Portal Access Options

| Method | Portal | Capabilities | Our Access? |
|--------|--------|-------------|-------------|
| **Dealer Portal** (polarisdealers.com) | Full dealer tools | Real-time inventory, bulk ordering, pricing, TSBs | Requires dealer credentials |
| **Public Parts Catalog** (polaris.com) | Consumer-facing | Part lookup by VIN, exploded diagrams, pricing | Public access |
| **DMS Integration** (DX1, ASPEN, Commander) | Certified middleware | Automated order submission, inventory sync | Requires DMS subscription |

### Recommended Approach: Tiered Strategy

**Tier 1 (MVP) — Public Catalog Scraper + Manual Ordering**
- Playwright agent scrapes polaris.com parts catalog
- Generates a formatted parts list with part numbers and prices
- Mechanic takes the list and places order via phone/portal manually
- This gets us 80% of the value with minimal complexity

**Tier 2 (Production) — Dealer Portal Automation**
- If we have or obtain Polaris dealer credentials
- Playwright agent automates the full ordering workflow on polarisdealers.com
- This is the same proven pattern as our MPOWR agents

**Tier 3 (Advanced) — DMS API Integration**
- Partner with a certified DMS provider (DX1 or ASPEN)
- Proper API integration for order submission
- Real-time inventory and pricing
- Most reliable but highest cost/complexity

---

## Tier 1: Public Catalog Scraper Agent

### Architecture

```python
class PolarisPartsScraper:
    """Scrapes the Polaris public parts catalog for part information."""
    
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None
        self.base_url = "https://www.polaris.com/en-us/parts/"
    
    async def lookup_parts_by_vin(self, vin: str, assembly_category: str):
        """
        Navigate to Polaris parts catalog, enter VIN, and extract
        part information for a specific assembly category.
        
        Returns: List of parts with numbers, names, prices, and diagram images
        """
        # 1. Navigate to parts catalog
        await self.page.goto(self.base_url)
        
        # 2. Enter VIN in vehicle selector
        await self._select_vehicle_by_vin(vin)
        
        # 3. Navigate to assembly category
        await self._navigate_to_assembly(assembly_category)
        
        # 4. Extract exploded diagram image
        diagram_url = await self._extract_diagram_image()
        
        # 5. Extract parts list from diagram legend
        parts = await self._extract_parts_list()
        
        return {
            "assembly": assembly_category,
            "diagram_url": diagram_url,
            "parts": parts
        }
    
    async def verify_part_number(self, part_number: str):
        """Verify a part number exists and get current pricing."""
        # Search by part number directly
        await self.page.goto(f"{self.base_url}?q={part_number}")
        # Extract result...
    
    async def bulk_catalog_export(self, vin: str):
        """Export ALL parts for a vehicle (full catalog build)."""
        categories = await self._get_all_categories(vin)
        all_parts = []
        for category in categories:
            parts = await self.lookup_parts_by_vin(vin, category)
            all_parts.extend(parts)
            await asyncio.sleep(2)  # Be respectful with rate limiting
        return all_parts
```

### Catalog Sync Schedule

- **Full rebuild:** Monthly (overnight job — takes several hours per vehicle)
- **Targeted refresh:** On-demand when a part lookup returns stale data
- **Supersession check:** Weekly for frequently-ordered parts

---

## Tier 2: Dealer Portal Order Automation

This follows the **exact same Playwright pattern** we use for MPOWR. The `PolarisOrderAgent` would be structured identically to `MpowrCreatorBot`.

### Order Submission Workflow

```python
class PolarisOrderAgent:
    """Automates parts ordering through the Polaris dealer portal."""
    
    def __init__(self):
        self.browser = None
        self.page = None
    
    async def submit_order(self, order: PartsOrder):
        """
        Full order submission workflow:
        1. Login to dealer portal
        2. Navigate to parts ordering
        3. Add each part to cart
        4. Verify pricing and availability
        5. Submit order
        6. Capture confirmation number
        """
        # 1. Login
        await self._login(email=POLARIS_DEALER_EMAIL, 
                         password=POLARIS_DEALER_PASSWORD)
        
        # 2. Navigate to order entry
        await self._navigate_to_order_entry()
        
        # 3. Add parts
        for part in order.parts:
            result = await self._add_part_to_cart(
                part_number=part.part_number,
                quantity=part.quantity
            )
            if not result.success:
                order.flag_issue(part, result.error)
        
        # 4. Review cart
        cart_summary = await self._review_cart()
        
        # 5. Submit if all parts available
        if cart_summary.all_available:
            confirmation = await self._submit_order()
            await self._log_order(order, confirmation)
            await self._notify_slack(order, confirmation)
            return confirmation
        else:
            # Some parts unavailable — return for human review
            return cart_summary
```

### Error Handling & Retry Logic

Apply same patterns as MPOWR agents:
- Screenshot on every failure
- Retry with exponential backoff (3 attempts)
- Slack alert on final failure
- All orders logged to Supabase for audit trail

---

## Parts List Document Format

The editable parts document that mechanics review before ordering:

```json
{
  "session_id": "uuid-xxx",
  "vehicle": {
    "unit_id": "RZR-07",
    "vin": "3NSRZE999RF123456",
    "model": "RZR XP 1000",
    "year": 2024
  },
  "diagnosis": "Front left CV axle failure with probable wheel bearing damage",
  "parts": [
    {
      "line": 1,
      "part_number": "1334441",
      "description": "CV Axle Assembly, Front LH",
      "quantity": 1,
      "unit_price": 289.99,
      "category": "Front Drivetrain",
      "source": "ai_recommended",
      "status": "approved",
      "notes": ""
    },
    {
      "line": 2,
      "part_number": "3514699",
      "description": "Wheel Bearing, Front",
      "quantity": 1,
      "unit_price": 45.99,
      "category": "Front Suspension",
      "source": "ai_recommended",
      "status": "approved",
      "notes": "Mechanic confirmed wheel play during inspection"
    }
  ],
  "subtotal": 374.95,
  "created_at": "2026-04-28T12:30:00Z",
  "approved_by": "Mike T.",
  "approved_at": "2026-04-28T12:35:00Z"
}
```

---

*Continue to → [05_FRONTEND_UX.md](./05_FRONTEND_UX.md)*
