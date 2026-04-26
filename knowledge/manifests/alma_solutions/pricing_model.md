# Concept: Pricing Model

## Overview
Beh Brothers Electric pricing structure for estimating and invoicing.

## Labor Rates

| Rate Type | Amount | Notes |
|-----------|--------|-------|
| Standard Hourly | $125/hr | Per man-hour |
| Emergency/After Hours | $187.50/hr | 1.5x standard |

## Parts Markup

| Markup Type | Percentage | Notes |
|-------------|------------|-------|
| Standard | 30% | Applied to cost |
| Specialty/Custom | 35-40% | Hard-to-source items |

## Calculation Formula
```
Labor Total = (Number of Workers) × (Hours) × (Hourly Rate)
Parts Total = (Parts Cost) × (1 + Markup Percentage)
Job Total = Labor Total + Parts Total
```

## Job Templates

| Job Type | Base Hours | Workers | Est. Revenue |
|----------|-----------|---------|--------------|
| 200A Overhead Service Upgrade | 8 | 2 | $2,500-3,000 |
| 200A Underground Service Upgrade | 6 | 2 | $2,000-2,500 |
| 100A Service Upgrade | 6 | 2 | $1,800-2,200 |
| Subpanel Installation | 4 | 1 | $800-1,200 |
| EV Charger (Level 2) | 4 | 1 | $800-1,200 |
| EV Charger (Long Run) | 6 | 2 | $1,200-1,800 |
| Recessed Lighting | 0.5/light | 1 | $75-100/light |
| Ceiling Fan Installation | 1.5 | 1 | $200-300 |
| GFCI Outlet Installation | 1 | 1 | $150-200 |
| Dedicated 20A Circuit | 2 | 1 | $350-450 |
| Whole House Surge Protector | 1.5 | 1 | $400-500 |
| Smoke/CO Detector Install | 0.5/unit | 1 | $100-150/unit |
| Electrical Troubleshooting | 2 | 1 | $250+ |
| Panel Inspection | 1 | 1 | $125 |

## Estimate Adjustments

### Complexity Factors
- **Easy Access**: No adjustment
- **Attic/Crawlspace**: +15-25% labor
- **Difficult Terrain**: +10-20% labor

### Travel Distance
- **Local (Monticello)**: No charge
- **Moab Area**: +$50-100 trip charge

## Related Files
- `directives/operations_management.md`
- `brain/sources/price_book.csv`
- `execution/modules/estimates.py`
