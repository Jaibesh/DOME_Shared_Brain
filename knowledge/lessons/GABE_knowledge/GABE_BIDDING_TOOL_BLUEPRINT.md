# Blueprint: Gabe's Dirtwork Bidding Tool (Google Sheets)

This document provides the full structural specifications and logic required to build a professional bidding and estimation tool for Gabe's Dirtwork using Google Sheets.

---

## 1. Core Architecture
The spreadsheet should consist of the following tabs:

1.  **Dashboard**: High-level view of active bids, win rates, and upcoming projects.
2.  **Project Intake**: Data entry for new leads and site conditions.
3.  **Calculator (Estimator)**: The "engine" where dimensions, soil types, and equipment hours are calculated.
4.  **Price Book**: A master list of equipment rates, material costs, and labor overhead.
5.  **Bid Generator**: A formatted, print-ready sheet that pulls data from the Calculator to create a formal quote.
6.  **Archive**: Record of completed/lost bids for historical data.

---

## 2. Tab Specifications

### A. Price Book (The Foundation)
*Maintain this sheet to update rates across all new bids.*

| Category | Item Name | Unit | Rate ($) | Notes |
| :--- | :--- | :--- | :--- | :--- |
| Equipment | Excavator (Large) | Per Hour | 225.00 | Includes Operator |
| Equipment | Dozer (D6) | Per Hour | 250.00 | Includes Operator |
| Equipment | Skid Steer | Per Hour | 125.00 | Includes Operator |
| Materials | Road Base | Per Ton | 45.00 | Delivered |
| Materials | Fill Dirt | Per Load | 150.00 | 12-yard dump |
| Labor | General Labor | Per Hour | 45.00 | Ground crew |
| Fees | Mobilization | Flat | 500.00 | Base (within 30 miles) |

### B. Project Intake (Lead Data)
| Column | Description |
| :--- | :--- |
| Project ID | Auto-generated or custom (e.g., 2024-001) |
| Client Name | Contact person |
| Site Address | Physical location |
| Soil Type | Dropdown: Caliche, Sand, Clay, Rock, Mixed |
| Vegetation | Dropdown: Clear, Light Brush, Heavy Wooded |
| Project Scope | Checkboxes: Clearing, Grading, Pad Prep, Trenching |

### C. Calculator (The Engine)
*This is where the math happens.*

#### **Key Formulas:**
1.  **Cubic Yardage (Cut/Fill):**
    `=(Length * Width * (Depth/12)) / 27` (Assuming depth is in inches)
2.  **Machine Time Estimation:**
    `=Total_Yards / Machine_Productivity_Rate`
    *Note: Productivity rates vary by soil. Example: A D6 moves ~100 yds/hr in Loose Soil vs ~60 yds/hr in Caliche.*

#### **Logic Table Structure:**
| Task | Equipment | Qty/Sft/Yds | Productivity (Unit/Hr) | Estimated Hours | Rate | Total Cost |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Pad Grading | Dozer | 5000 | 250 | 20 | $250 | $5,000 |
| Trenching | Excavator | 350 | 50 | 7 | $225 | $1,575 |

---

## 3. The Bid Generator (Output)
*This tab should be formatted to look like a professional Invoice/Quote.*

*   **Header**: Gabe's Dirtwork Logo & Contact Info.
*   **Customer Info**: Linked from "Project Intake".
*   **Scope of Work**: A text block describing what is included (e.g., "Clearing of 2 acres including stump removal").
*   **Line Items**: Summarized from "Calculator" (e.g., "Site Preparation", "Material Delivery", "Final Grade").
*   **Exclusions**: Standard text: "Assumes no rock excavation unless specified", "811 must be called before arrival".
*   **Total**: Sum of line items + Margin (usually 15-20%).

---

## 4. Advanced Logic & Automation

### Soil Difficulty Multiplier
In the Calculator, use a multiplier based on the Soil Type selected in Intake:
*   **Sand**: 1.0 (Standard)
*   **Clay**: 1.2 (20% slower)
*   **Caliche**: 1.5 (50% slower)
*   **Rock**: 2.5+ (Requires specialized equipment)

### Margin Protection
Calculate the "Break-even" cost (Fuel + Operator + Maintenance) and apply a **Gross Margin Target**.
`Total Bid = Break-Even / (1 - Target_Margin%)`
Example: If cost is $10k and you want 20% margin: `10000 / 0.80 = $12,500`.

---

## 5. Step-by-Step Build Instructions

1.  **Setup Styles**: Use alternating row colors for readability and bold headers.
2.  **Data Validation**: Use `Data > Data Validation` to create dropdowns for Soil Types and Equipment Names.
3.  **VLOOKUPs**: Use `VLOOKUP` to fetch rates from the **Price Book** into the **Calculator**.
    `=VLOOKUP(Equipment_Name, 'Price Book'!A:D, 4, FALSE)`
4.  **Formatting**: Ensure the **Bid Generator** is set to "Print Selection" and fits on one page.

---

**Next Steps**:
*   Gabe to provide actual equipment rates.
*   Define "Productivity Rates" for specific machines (e.g., how many yards a Skid Steer can move per hour).
*   Test with a sample 10-acre warehouse site prep project.
