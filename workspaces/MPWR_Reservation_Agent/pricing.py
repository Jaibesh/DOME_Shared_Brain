import math

# Baseline pricing for Tours
# Key: MPOWR Activity Name -> Vehicle -> Base Price
TOUR_PRICING = {
    "Hell's Revenge": {
        "RZR XP S": 318.00,        # 1-2 people
        "RZR XP4 S": 459.00,       # 3-4 people
        "RZR Pro R": 411.00,
        "Guide Car": 99.00
    },
    "Poison Spider Mesa": {
        "RZR Pro R": 479.00,
        "Guide Car": 149.00
    },
    "Moab Discovery Tour": {
        "XPEDITION XP 5 NorthStar": 329.00,
        "Guide Car": 149.00
    }
}

# Baseline pricing for Rentals
# Key: Duration -> Vehicle -> Base Price
RENTAL_PRICING = {
    "3 Hour": {
        "RZR XP S": 289.00,
        "RZR XP4 S": 339.00,
        "Turbo Pro S": 374.00,
        "RZR PRO S4": 374.00,
        "RZR Pro R": 422.00
    },
    "Half-Day": {
        "RZR XP S": 339.00,
        "RZR XP4 S": 389.00,
        "Turbo Pro S": 442.00,
        "RZR PRO S4": 442.00,
        "RZR Pro R": 489.00
    },
    "Full-Day": {
        "RZR XP S": 389.00,
        "RZR XP4 S": 439.00,
        "Turbo Pro S": 499.00,
        "RZR PRO S4": 499.00,
        "RZR Pro R": 579.00
    },
    "24 Hour": {
        "RZR XP S": 439.00,
        "RZR XP4 S": 489.00,
        "Turbo Pro S": 549.00,
        "RZR PRO S4": 549.00,
        "RZR Pro R": 679.00
    },
    "Multi-Day": { # Default to 2-Day base for math splitting
        "RZR XP S": 749.00,
        "RZR XP4 S": 839.00,
        "Turbo Pro S": 1048.00,
        "RZR PRO S4": 1048.00,
        "RZR Pro R": 1258.00
    }
}

def get_baseline_price(booking_type: str, mpowr_activity: str, duration: str, mpowr_vehicle: str) -> float:
    """Gets the baseline price to be used for proportional subtotal splitting."""
    try:
        if booking_type == "tour":
            if mpowr_activity in TOUR_PRICING:
                # Fallbacks for tour vehicles
                v = mpowr_vehicle
                if v not in TOUR_PRICING[mpowr_activity]:
                    # Default to cheapest if unknown
                    return min(TOUR_PRICING[mpowr_activity].values())
                return TOUR_PRICING[mpowr_activity][v]
            return 300.0 # Safe default
        else:
            # Rental
            dur = "Half-Day"
            if "3 Hour" in duration: dur = "3 Hour"
            elif "Half" in duration: dur = "Half-Day"
            elif "Full" in duration: dur = "Full-Day"
            elif "24" in duration: dur = "24 Hour"
            elif "Day" in duration: dur = "Multi-Day"

            if dur in RENTAL_PRICING:
                if mpowr_vehicle in RENTAL_PRICING[dur]:
                    return RENTAL_PRICING[dur][mpowr_vehicle]
                return min(RENTAL_PRICING[dur].values())
            return 400.0
    except Exception:
        return 350.0

def split_subtotal(payloads: list[dict], total_subtotal: float) -> list[dict]:
    """Splits the grand subtotal proportionally among the payloads based on their baseline value."""
    if len(payloads) == 1:
        payloads[0]["target_price"] = total_subtotal
        return payloads

    total_baseline = 0
    for p in payloads:
        base = get_baseline_price(p["booking_type"], p["mpowr_activity"], p.get("ticket_duration_string", ""), p["mpowr_vehicle"]) * p.get("vehicle_qty", 1)
        p["_baseline_val"] = base
        total_baseline += base

    if total_baseline == 0:
        # Fallback to even split
        split = round(total_subtotal / len(payloads), 2)
        for p in payloads:
            p["target_price"] = split
    else:
        # Proportional split
        accumulated = 0
        for i, p in enumerate(payloads):
            if i == len(payloads) - 1:
                # Last item gets the exact remainder to prevent rounding missing pennies
                p["target_price"] = round(total_subtotal - accumulated, 2)
            else:
                share = round(total_subtotal * (p["_baseline_val"] / total_baseline), 2)
                p["target_price"] = share
                accumulated += share

    return payloads
