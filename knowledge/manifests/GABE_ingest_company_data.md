# Ingest Company Data Directive

**Goal:** Analyze exported Housecall Pro data to create a persistent "Company Profile" that guides future agent decisions.

## Inputs
- `brain/sources/housecall_data/*.csv`
    - Expects `price_book_materials.csv`
    - Expects `job_history.csv`

## Process
1.  **Locate Files:** Search the `brain/sources/housecall_data/` directory. If empty, ask the user to upload files.
2.  **Analyze Price Book:**
    - Identify **Top Brands** (e.g., "Leviton", "Lutron", "Square D").
    - Calculate **Average Part Markup** (if Cost and Price fields are populated).
    - Note specific **Naming Conventions** (e.g., do they use "Romex" or "NM-B"?).
3.  **Analyze Job History:**
    - Identify **Common Job Keywords** (e.g., "Service Call", "Rough in", "Panel Upgrade").
    - Identify **Standard Descriptions** (copying the tone/style of high-quality descriptions).
4.  **Generate Output:**
    - Write (or overwrite) `brain/company_profile.md`.

## Output Format (`brain/company_profile.md`)

```markdown
# Company Profile: [Company Name]

## Preferences
- **Preferred Brands**: [List extracted brands]
- **Wire Type**: [e.g., Mostly Romex, some MC]
- **Device Color**: [e.g., White is default]

## Pricing Model
- **Target Material Markup**: [e.g., ~1.5x cost]
- **Labor Rate Inference**: [Notes on labor if discernible]

## Common Scope patterns
- [Insight 1: e.g., "Panel upgrades are usually 200A"]
- [Insight 2: e.g., "Kitchens always include under-cabinet lighting"]
```

## Usage
Once created, `brain/company_profile.md` should be read by the `housecall_pro_manager` agent at the start of any estimation task to personalize the output.
