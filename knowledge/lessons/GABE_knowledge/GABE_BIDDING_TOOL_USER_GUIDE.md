# User Guide: Operating the Dirtwork Bidding Tool

This guide explains how Gabe or his team should use the Google Sheets Bidding Tool to generate accurate quotes and track projects.

---

## 1. Initial Setup (One-Time)
Before sending out your first bid, ensure the **Price Book** is accurate.
1.  Open the **Price Book** tab.
2.  Update the **Hourly Rates** for all equipment (Excavator, Dozer, etc.).
3.  Enter current **Fuel Surcharges** if applicable.
4.  Input current **Material Costs** from your suppliers (Fill dirt, Road base).

---

## 2. Estimating a New Project

### Step A: Project Intake
1.  Go to the **Project Intake** tab.
2.  Fill in the client name, address, and project type.
3.  **Critical**: Select the **Soil Type**. This automatically adjusts the time estimates in the back-end calculator.
4.  Note any "Red Flags" (e.g., proximity to power lines, tight access).

### Step B: The Calculator
1.  Go to the **Calculator** tab.
2.  Enter the dimensions of the area to be worked (Length, Width, and average Depth of cut/fill).
3.  Select the equipment you plan to use for each line item.
4.  Review the **Estimated Hours**. If you believe the job will take longer due to site-specific quirks, manually override the hour count.
5.  Check the **Materials** section. Enter the volume needed based on the yardage calculated.

### Step C: Review Margin
1.  Look at the **Gross Margin** indicator at the bottom. 
2.  Adjust your "Profit %" (Markup) based on how much you want the job or how risky it is.
    *   *Low Risk*: 15-20% margin.
    *   *High Risk (Unknown site)*: 25-35% margin.

---

## 3. Generating the Bid
1.  Go to the **Bid Generator** tab.
2.  Ensure everything looks professional.
3.  Check the "Assumptions & Exclusions" section to make sure it covers the specific project.
4.  Go to `File > Print` or `File > Download > PDF`.
5.  Send to the client.

---

## 4. Best Practices for Accurate Bids
*   **The "Rock" Factor**: Always include a clause that rock excavation is "extra" unless a soil report is provided.
*   **Mobilization**: Don't forget the cost of your time and fuel to move the machines. If it's more than 50 miles, double your mobilization fee.
*   **Weather Days**: If the project is scheduled for a rainy season, add a 5% "weather contingency" to the labor/equipment time.

---

## 5. Maintenance
*   Review your **Price Book** every 3 months.
*   Compare your "Estimated Hours" vs "Actual Hours" after every job. If you find you are consistently taking longer than the tool predicts, lower the **Productivity Rate** in the hidden logic settings.
