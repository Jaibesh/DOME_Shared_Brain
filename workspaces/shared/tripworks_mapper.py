"""
data_mapper.py — TripWorks ↔ MPOWR Translation Layer

Handles all conversion between Google Sheets / TripWorks data formats
and MPOWR form field values. Includes:
- Activity/listing mapping
- Vehicle model mapping
- Ticket Type parsing (model, rider config, quantity, duration)
- Webhook email construction
- Price parsing (Sub-Total cents → dollars)
- Time slot selection (nearest ≤ target)
- Guide add-on decision tree
- Insurance selection
"""

import re
from datetime import datetime


# =============================================================================
# ACTIVITY MAPPING: Google Sheet 'Activity' → MPOWR Activity Name
# =============================================================================
# CONFIRMED via live MPOWR DOM exploration — April 10, 2026
# These are the exact text strings that appear in the MPOWR UI.

TOUR_ACTIVITY_MAP = {
    "Gateway to Hell's Revenge and Fins N' Things": "Hell's Revenge",
    "Gateway to Hell's": "Hell's Revenge",
    "Hell's Revenge - Pro R Ultimate Experience": "Hell's Revenge",
    "Hell's Revenge and Fins N' Things - Private": "Hell's Revenge",
    "Private Pro R - Hell's Revenge": "Hell's Revenge",
    "TripAdvisor Exclusive Hell's and Fins": "Hell's Revenge",
    "Pro R - Adult Hell's": "Hell's Revenge",
    "Poison Spider - Private": "Poison Spider Mesa",
    "Poison Spider Mesa Tour": "Poison Spider Mesa",
    "Moab Discovery Tour": "Moab Discovery Tour",
    "Moab Discovery": "Moab Discovery Tour",
}

# Rental Duration (from Ticket Type) → MPOWR Rental Activity
# These are substring-matched with exact=False in Playwright
# Multiple variants of the same duration are mapped to handle inconsistent data entry
RENTAL_DURATION_MAP = {
    "3 Hours": "3 Hour Self-Guided Adventure Rental",
    "3 Hour": "3 Hour Self-Guided Adventure Rental",
    "3hr": "3 Hour Self-Guided Adventure Rental",
    "Half-Day Up to 5 Hours": "Half-Day Self-Guided Rental",
    "Half-Day": "Half-Day Self-Guided Rental",
    "Half Day": "Half-Day Self-Guided Rental",
    "Full-Day Up to 9 Hours": "Full-Day Adventure",
    "Full-Day": "Full-Day Adventure",
    "Full Day": "Full-Day Adventure",
    "24 Hours": "24 Hour Rental",
    "24 Hour": "24 Hour Rental",
    "24hr": "24 Hour Rental",
    "2-Day Rental": "Multi-Day Adventure Rental",
    "2-Day": "Multi-Day Adventure Rental",
    "2 Day": "Multi-Day Adventure Rental",
    "3-Day Rental": "Multi-Day Adventure Rental",
    "3-Day": "Multi-Day Adventure Rental",
    "3 Day": "Multi-Day Adventure Rental",
    "4-Day Rental": "Multi-Day Adventure Rental",
    "4-Day": "Multi-Day Adventure Rental",
    "4 Day": "Multi-Day Adventure Rental",
    "5-Day Rental": "Multi-Day Adventure Rental",
    "5-Day": "Multi-Day Adventure Rental",
    "5 Day": "Multi-Day Adventure Rental",
    "6-Day Rental": "Multi-Day Adventure Rental",
    "6-Day": "Multi-Day Adventure Rental",
    "6 Day": "Multi-Day Adventure Rental",
    "7-Day Rental": "Multi-Day Adventure Rental",
    "7-Day": "Multi-Day Adventure Rental",
    "7 Day": "Multi-Day Adventure Rental",
    "Multi-Day": "Multi-Day Adventure Rental",
}

# Vehicle model keywords (from Ticket Type) → MPOWR vehicle card text
# CONFIRMED exact names from live screenshots
VEHICLE_MODEL_MAP = {
    "RZR 1000": "RZR XP4 S",                    # 4-seat, $159/tour
    "XP S 1000": "RZR XP4 S",                   # 4-seat variant
    "XP S": "RZR XP S",                          # 2-seat, rentals only
    "Pro R": "RZR Pro R",                         # 2-seat, $205/tour
    "Turbo Pro S": "RZR PRO S",                  # MPOWR calls it "RZR PRO S" not "Turbo"
    "PRO S4": "RZR PRO S4",                      # 4-seat Pro S
    "Xpedition": "XPEDITION XP 5 NorthStar",    # 5-seat, Moab Discovery only
    "XP5": "XPEDITION XP 5 NorthStar",           # Alias
}

# Rental Activity (from Sheet 'Activity' column) → vehicle model string
# The Activity column for rentals specifies the VEHICLE, not the duration.
# Duration comes from the Ticket Type column.
#
# CRITICAL: Entries are ordered LONGEST-FIRST so that substring matching
# always picks the most specific key before a shorter partial match.
# e.g. "2026 2-Seat Polaris RZR XP S 1000 Ultimate" must match before "XP S 1000"
RENTAL_VEHICLE_MAP = {
    # --- Full 2026 model names (most specific — checked first) ---
    "2026 4-Seat Polaris RZR XP S 1000 Ultimate": "XP S 1000",  # 4-seat XPS
    "2026 2-Seat Polaris RZR XP S 1000 Ultimate": "XP S",       # 2-seat XPS (NOT XP S 1000!)
    "2026 4-Seat RZR Turbo Pro S 1000 Ultimate": "PRO S4",      # 4-seat Pro S
    "2026 2-Seat RZR Turbo Pro S 1000 Ultimate": "Turbo Pro S", # 2-seat Pro S
    "2026 2-Seat RZR Pro R Ultimate": "Pro R",
    # --- Short-form rental names ---
    "4-Seat Pro S Rental": "PRO S4",
    "2-Seat Pro S Rental": "Turbo Pro S",
    "4-Seat ProS Rental": "PRO S4",
    "2-Seat ProS Rental": "Turbo Pro S",
    "4-Seat XP S Rental": "XP S 1000",
    "2-Seat XP S Rental": "XP S",
    "4-Seat XPS Rental": "XP S 1000",
    "2-Seat XPS Rental": "XP S",
    "4-Seat Pro R Rental": "Pro R",
    "2-Seat Pro R Rental": "Pro R",
    # Catch-all: any mention of Pro R in activity
    "Pro R": "Pro R",
}

# Activities that are tours (vs rentals)
TOUR_ACTIVITIES = set(TOUR_ACTIVITY_MAP.keys())

# Tours that ALWAYS use Pro R
# EDGE-8 FIX: Use TOUR_ACTIVITY_MAP keys (substrings) instead of full activity names.
# These must be substrings that appear in the Activity column, not full strings.
PRO_R_TOURS = {
    "Pro R Ultimate",
    "Poison Spider - Private",
    "Poison Spider Mesa Tour",
    "Private Pro R",
    "Pro R - Adult",
}

# Tours that ALWAYS use Xpedition XP5
XP5_TOURS = {
    "Moab Discovery Tour",
    "Moab Discovery",
}


# =============================================================================
# WEBHOOK EMAIL
# =============================================================================

def build_webhook_email(tw_confirmation: str) -> str:
    """
    Builds the MPOWR email field value using the webhook format.
    NOT the customer's real email — this links TripWorks to MPOWR.

    Example: "CO-D5A-8KY" → "polaris+CO-D5A-8KY@epic4x4adventures.com"
    """
    return f"polaris+{tw_confirmation.strip()}@epic4x4adventures.com"


# =============================================================================
# TICKET TYPE PARSING
# =============================================================================

def parse_ticket_type(ticket_type: str, activity: str) -> dict:
    """
    Parses the Ticket Type column into structured data.

    Tour examples:
        "2026 RZR 1000 for 1 - 2 People x3, Guest Waiver x2"
        → {"model": "RZR 1000", "rider_config": "1-2", "vehicle_qty": 3, "duration": None,
           "guide_breakdown": [{"rider_config": "1-2", "qty": 3}]}

        "2026 RZR 1000 for 1 - 2 People x2, 2026 RZR 1000 for 3 - 4 People x1"
        → {"model": "RZR 1000", "rider_config": "1-2", "vehicle_qty": 3, "duration": None,
           "guide_breakdown": [{"rider_config": "1-2", "qty": 2}, {"rider_config": "3-4", "qty": 1}]}

        "2026 RZR Pro R for 1 - 2 People x1"
        → {"model": "Pro R", "rider_config": "1-2", "vehicle_qty": 1, "duration": None,
           "guide_breakdown": [{"rider_config": "1-2", "qty": 1}]}

    Rental examples:
        "Half-Day Up to 5 Hours x2"
        → {"model": None, "rider_config": None, "vehicle_qty": 2, "duration": "Half-Day Up to 5 Hours",
           "guide_breakdown": []}

    Args:
        ticket_type: Raw Ticket Type string from Google Sheet
        activity: The Activity column value (to determine tour vs rental)

    Returns:
        Dict with model, rider_config, vehicle_qty, duration, guide_breakdown
    """
    if not ticket_type:
        return {"model": None, "rider_config": None, "vehicle_qty": 1, "duration": None, "guide_breakdown": []}

    is_tour = is_tour_activity(activity)
    result = {
        "model": None,
        "rider_config": None,
        "vehicle_qty": 1,
        "duration": None,
        "guide_breakdown": [],  # List of {"rider_config": "1-2", "qty": N}
    }

    total_vehicle_qty = 0

    # Split on comma to handle multiple ticket items
    # e.g. "2026 RZR 1000 for 1 - 2 People x2, 2026 RZR 1000 for 3 - 4 People x1"
    parts = [p.strip() for p in ticket_type.split(",")]

    for part in parts:
        # Skip non-vehicle entries like "Guest Waiver x2", "Adult riders", or "Passengers"
        if "guest waiver" in part.lower() or "waiver" in part.lower() or "adult rider" in part.lower() or "passenger" in part.lower() or "rider" in part.lower():
            continue

        # Extract quantity (e.g., "x3" at the end)
        qty_match = re.search(r'x(\d+)\s*$', part, re.IGNORECASE)
        if qty_match:
            qty = int(qty_match.group(1))
        else:
            # Fallback: try to find a leading small quantity like "2 RZR" or "3 Pro R"
            # IMPORTANT: Exclude model years (2024, 2025, 2026, etc.)
            qty_fallback = re.search(r'\b([1-9])\s+(?:RZR|XP|Pro|Xpedition|seat|Turbo)', part, re.IGNORECASE)
            qty = int(qty_fallback.group(1)) if qty_fallback else 1

        if is_tour:
            # Parse vehicle model
            if "pro r" in part.lower():
                result["model"] = "Pro R"
            elif "turbo" in part.lower():
                result["model"] = "Turbo Pro S"
            elif "1000" in part or "xp s" in part.lower():
                result["model"] = "RZR 1000"
            elif "xpedition" in part.lower() or "xp5" in part.lower():
                result["model"] = "Xpedition"

            # Parse rider configuration and build guide breakdown
            rider_match = re.search(r'(\d+)\s*-\s*(\d+)\s*people', part, re.IGNORECASE)
            if rider_match:
                rider_cfg = f"{rider_match.group(1)}-{rider_match.group(2)}"
                result["rider_config"] = rider_cfg  # Keep last one for backward compat
                result["guide_breakdown"].append({
                    "rider_config": rider_cfg,
                    "qty": qty,
                })

            total_vehicle_qty += qty

        else:
            # Rental: parse duration
            for duration_key in RENTAL_DURATION_MAP:
                if duration_key.lower() in part.lower():
                    result["duration"] = duration_key
                    break

            total_vehicle_qty += qty

    # Set total vehicle qty
    result["vehicle_qty"] = total_vehicle_qty if total_vehicle_qty > 0 else 1
    
    # SAFETY: Hard cap at 10 vehicles — anything higher is a parsing error
    if result["vehicle_qty"] > 10:
        result["vehicle_qty"] = 1

    # For tours with known fixed vehicles, override model from activity
    if is_tour:
        if any(t in activity for t in PRO_R_TOURS):
            result["model"] = "Pro R"
        elif any(t in activity for t in XP5_TOURS):
            result["model"] = "Xpedition"

    return result


# =============================================================================
# PRICE PARSING
# =============================================================================

def parse_subtotal(raw_value) -> float:
    """
    Converts the Sub-Total column to a dollar amount.

    IMPORTANT: The Google Sheets fetch uses `value_render_option="FORMATTED_VALUE"`
    which returns currency as "$1,855.00" (string with decimal). This is the
    expected path and bypasses all ambiguity.

    Fallback handling for edge cases:
        "$1,855.00" → $1855.00  (standard formatted value — preferred path)
        "1855.00"   → $1855.00  (decimal present = already dollars)
        185500      → $1855.00  (raw integer, clearly cents)
        "1855"      → $1855.00  (no decimal, treat as whole dollars)
        "$95.00"    → $95.00    (small dollar amount)

    Conservative rule: if there's a decimal point, trust it as dollars.
    If no decimal and value > 999, it might be cents — divide by 100.
    """
    if raw_value is None or raw_value == "":
        return 0.0

    # Convert to string and clean
    s = str(raw_value).replace("$", "").replace(",", "").strip()

    try:
        num = float(s)
    except ValueError:
        return 0.0

    # If there's a decimal point in the original string, trust it as dollars
    if "." in s:
        return num

    # No decimal point — this is a raw integer from Sheets/Zapier
    # Formatted dollar values ALWAYS have a decimal (e.g., "$358.61", "$95.00")
    # So any integer > 999 without a decimal is almost certainly cents from TripWorks API
    # Examples: 35861 = $358.61, 31800 = $318.00, 185500 = $1855.00
    if num > 999:
        return num / 100.0

    # Small integers (< 1000) are ambiguous but likely dollars (e.g. 95 = $95, 318 = $318)
    return num


# =============================================================================
# TIME SLOT SELECTION
# =============================================================================

def parse_time_string(time_str: str) -> datetime:
    """Parse a time string into a datetime for comparison.

    Handles all formats seen in the wild:
      - '5:15 PM', '9:00 AM'       (standard with space)
      - '5:15PM', '9:00AM'         (no space before AM/PM)
      - '5pm', '9am', '10am'       (bare hour, lowercase from normalizer)
      - '5PM', '9AM', '10AM'       (bare hour, uppercase)
      - '14:30'                     (24-hour)
      - '5:30 am', '8:30 am'       (with space, from MPOWR dropdown)
    """
    import re
    time_str = str(time_str).strip()
    
    # Handle Google Sheets serial time values (fraction of a day, e.g. 0.7604166667 = 6:15 PM)
    try:
        serial = float(time_str)
        if 0 < serial < 1:
            total_minutes = round(serial * 24 * 60)
            hours = total_minutes // 60
            minutes = total_minutes % 60
            period = "AM" if hours < 12 else "PM"
            display_hour = hours if hours <= 12 else hours - 12
            if display_hour == 0: display_hour = 12
            time_str = f"{display_hour}:{minutes:02d} {period}"
    except (ValueError, TypeError):
        pass

    # Normalize: add space before AM/PM if missing (e.g. '10AM' → '10 AM')
    time_str = re.sub(r'(\d)(am|pm)', r'\1 \2', time_str, flags=re.IGNORECASE)
    time_str = time_str.upper().strip()

    # If it's just a bare number + AM/PM (e.g. '10 AM'), add ':00'
    match = re.match(r'^(\d{1,2})\s*(AM|PM)$', time_str)
    if match:
        time_str = f"{match.group(1)}:00 {match.group(2)}"

    for fmt in ["%I:%M %p", "%I:%M%p", "%H:%M", "%H:%M:%S", "%I %p"]:
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse time: '{time_str}'")


def select_best_time_slot(available_times: list[str], target_time: str) -> str | None:
    """
    Selects the best matching MPOWR time slot.

    Strategy: Pick the NEAREST available time by absolute distance.
    If two slots are equidistant, prefer the one AT or BEFORE the target.

    This is simpler and more intuitive than the old "nearest ≤ only" rule,
    which caused '4:45pm' to pick '9am' instead of '5pm' when only
    ['9am', '5pm'] were available.

    Examples:
        target="5:15 PM", available=["4:00 PM","5:00 PM","5:30 PM"] → "5:00 PM"
        target="9:00 AM", available=["9:00 AM","9:30 AM"]           → "9:00 AM"
        target="8:45 AM", available=["8:00 AM","8:30 AM","9:00 AM"] → "8:30 AM"
        target="5:30 PM", available=["9:00 AM","5:00 PM"]           → "5:00 PM"
        target="4:00 PM", available=["9:00 AM","5:00 PM"]           → "5:00 PM"
        target="4:45 PM", available=["9:00 AM","5:00 PM"]           → "5:00 PM"
        target="7:00 AM", available=["8:00 AM","9:00 AM"]           → "8:00 AM"
    """
    if not available_times or not target_time:
        return None

    try:
        target_dt = parse_time_string(target_time)
    except ValueError:
        # Can't parse target — return first available
        print(f"  ⚠️ Cannot parse target time '{target_time}'. Using first available.")
        return available_times[0] if available_times else None

    best_slot = None
    best_distance = None
    best_is_before = False

    for slot in available_times:
        try:
            slot_dt = parse_time_string(slot)
        except ValueError:
            continue

        distance = abs((slot_dt - target_dt).total_seconds())
        is_before = slot_dt <= target_dt

        # Pick this slot if:
        # 1. No best yet, or
        # 2. Closer by absolute distance, or
        # 3. Same distance but this one is at-or-before (tiebreaker)
        if (best_distance is None or
            distance < best_distance or
            (distance == best_distance and is_before and not best_is_before)):
            best_slot = slot
            best_distance = distance
            best_is_before = is_before

    if best_slot and not best_is_before:
        print(f"  ⚠️ No slot at/before '{target_time}'. Using nearest: '{best_slot}'")

    return best_slot


# =============================================================================
# GUIDE ADD-ON SELECTOR
# =============================================================================

class GuideAddonSelector:
    """
    Determines which guide add-on(s) to select for tours.

    IMPORTANT: A single reservation can require MULTIPLE different guide types.
    For example, 3 XP4 S vehicles on Hell's Revenge could need:
        - 2x "Gateway Party of 1-2 - Guide Services" ($159 each)
        - 1x "Gateway Party of 3 - 4 Guide Services" ($229)
    This happens when some vehicles carry 1-2 passengers and others carry 3-4.

    Decision tree:
    - Rentals: No guide add-on (return empty list)
    - Hell's Revenge (Gateway + Pro R Ultimate):
        - RZR Pro R: "Pro R Hell's Revenge Guide Services" ($206)
        - RZR XPS 1000: Mix of "1-2" and "3-4" based on guide_breakdown
    - Poison Spider: "Poison Spider Guide Services" x vehicle_qty
    - Moab Discovery Tour: "Moab Discovery Tour Guide Services" x vehicle_qty
    """

    # Guide add-on labels — these appear in the Rental Add-Ons search section
    # The bot types "Guide" into the search bar to display all options,
    # then clicks the specific "Add" button via aria-label
    HELLS_REVENGE_GUIDES = {
        "1-2": "Gateway Party of 1-2 - Guide Services",
        "3-4": "Gateway Party of 3 - 4 Guide Services",
        "Pro R": "Pro R Hell's Revenge Guide Services",
    }

    POISON_SPIDER_GUIDE = "Poison Spider Guide Services"
    DISCOVERY_GUIDE = "Moab Discovery Tour Guide Services"

    @classmethod
    def get_guide_selections(cls, activity: str, vehicle_model: str,
                             guide_breakdown: list, vehicle_qty: int) -> list:
        """
        Returns a LIST of guide add-on selections for tours.

        Uses the canonical MPOWR activity name (from TOUR_ACTIVITY_MAP) to
        determine which guide services apply. This ensures all aliases
        (e.g. "TripAdvisor Exclusive Hell's and Fins") route correctly
        without needing individual substring checks.

        Args:
            activity: Sheet Activity value (any alias)
            vehicle_model: Parsed from Ticket Type ("RZR 1000", "Pro R", "Xpedition")
            guide_breakdown: List of {"rider_config": "1-2", "qty": N} from parse_ticket_type
            vehicle_qty: Total number of vehicles

        Returns:
            List of {"label": "guide option label", "quantity": N}
            Empty list for rentals.

        Examples:
            Pro R x1 → [{"label": "Pro R Hell's Revenge Guide Services", "quantity": 1}]
            XP4 S x2 (1-2 people) → [{"label": "Gateway Party of 1-2 - Guide Services", "quantity": 2}]
            XP4 S x3 (2x 1-2, 1x 3-4) → [
                {"label": "Gateway Party of 1-2 - Guide Services", "quantity": 2},
                {"label": "Gateway Party of 3 - 4 Guide Services", "quantity": 1},
            ]
        """
        if not is_tour_activity(activity):
            return []  # Rentals get no guide

        # Resolve to canonical MPOWR name (e.g. "Hell's Revenge", "Poison Spider Mesa", "Moab Discovery Tour")
        normalized_activity = _normalize_apostrophes(activity)
        mpowr_name = None
        for tour_key, mapped_val in TOUR_ACTIVITY_MAP.items():
            if tour_key in normalized_activity:
                mpowr_name = mapped_val
                break

        if not mpowr_name:
            return []  # Unknown tour — let the bot flag it

        # Hell's Revenge tours (Gateway + Pro R Ultimate + TripAdvisor + all aliases)
        if mpowr_name == "Hell's Revenge":
            if vehicle_model == "Pro R":
                return [{
                    "label": cls.HELLS_REVENGE_GUIDES["Pro R"],
                    "quantity": vehicle_qty,
                }]
            else:
                # XPS 1000 / XP4 S — use guide_breakdown for mixed configs
                if guide_breakdown:
                    guides = []
                    for entry in guide_breakdown:
                        config = entry["rider_config"]
                        qty = entry["qty"]
                        if config in ("1-2", "3-4"):
                            guides.append({
                                "label": cls.HELLS_REVENGE_GUIDES[config],
                                "quantity": qty,
                            })
                        else:
                            # Default unknown configs to 1-2
                            guides.append({
                                "label": cls.HELLS_REVENGE_GUIDES["1-2"],
                                "quantity": qty,
                            })
                    return guides
                else:
                    # No breakdown available — default to 1-2 x vehicle_qty
                    return [{
                        "label": cls.HELLS_REVENGE_GUIDES["1-2"],
                        "quantity": vehicle_qty,
                    }]

        # Poison Spider tours
        if mpowr_name == "Poison Spider Mesa":
            return [{
                "label": cls.POISON_SPIDER_GUIDE,
                "quantity": vehicle_qty,
            }]

        # Moab Discovery Tour
        if mpowr_name == "Moab Discovery Tour":
            return [{
                "label": cls.DISCOVERY_GUIDE,
                "quantity": vehicle_qty,
            }]

        # Unknown tour — return empty and let the bot flag it
        return []


# =============================================================================
# INSURANCE SELECTOR
# =============================================================================

class InsuranceSelector:
    """
    Determines which AdventureAssure option to select.

    Current rule (Option A — ship fast):
    - Tours: ALWAYS free
    - Rentals: ALWAYS free (until insurance column exists in sheet)

    Future: Will read from an 'Insurance Choice' column when available.
    """

    # CONFIRMED from live MPOWR modal — both options are labeled "Free"
    FREE_INSURANCE_LABEL = "AdventureAssure Standard Protection"
    PAID_INSURANCE_LABEL = "AdventureAssure Upgraded Protection"

    @classmethod
    def get_insurance_selection(cls, booking_type: str,
                                insurance_choice: str = "free") -> str:
        """
        Returns the exact MPOWR label for the insurance option to select.

        Args:
            booking_type: 'tour' or 'rental'
            insurance_choice: 'free' or 'paid' (only matters for rentals, future use)
        """
        if insurance_choice == "paid":
            return cls.PAID_INSURANCE_LABEL
        return cls.FREE_INSURANCE_LABEL


# =============================================================================
# MASTER BUILDER: Sheet Row → CustomerPayload
# =============================================================================

def _normalize_apostrophes(s: str) -> str:
    """Normalize curly/smart apostrophes to straight for consistent matching."""
    return s.replace("\u2018", "'").replace("\u2019", "'")  # Left and right single quotes

def is_tour_activity(activity: str) -> bool:
    """Returns True if any known tour key is a substring of the activity.
    Handles curly vs straight apostrophe mismatches from Google Sheets.
    """
    normalized = _normalize_apostrophes(activity)
    return any(tour_key in normalized for tour_key in TOUR_ACTIVITIES)

def determine_booking_type(activity: str) -> str:
    """Returns 'tour' or 'rental' based on the Activity column."""
    return "tour" if is_tour_activity(activity) else "rental"


def get_mpowr_activity(activity: str, ticket_type_info: dict) -> str | None:
    """
    Returns the MPOWR activity/listing name to select in the dropdown.
    """
    # Tour — normalize apostrophes for consistent matching
    normalized = _normalize_apostrophes(activity)
    for tour_key, mapped_val in TOUR_ACTIVITY_MAP.items():
        if tour_key in normalized:
            return mapped_val

    # Rental — use duration
    duration = ticket_type_info.get("duration")
    if duration and duration in RENTAL_DURATION_MAP:
        return RENTAL_DURATION_MAP[duration]

    return None


def get_mpowr_vehicle(activity: str, ticket_type_info: dict) -> str | None:
    """
    Returns the MPOWR vehicle dropdown value.
    """
    booking_type = determine_booking_type(activity)
    normalized = _normalize_apostrophes(activity)

    if booking_type == "tour":
        model = ticket_type_info.get("model")
        if model and model in VEHICLE_MODEL_MAP:
            return VEHICLE_MODEL_MAP[model]
            
        # Fallback: check if activity explicitly forces a vehicle
        if any(t in normalized for t in PRO_R_TOURS):
            return VEHICLE_MODEL_MAP["Pro R"]
        if any(t in normalized for t in XP5_TOURS):
            return VEHICLE_MODEL_MAP["Xpedition"]
            
        # Supreme Fallback
        return VEHICLE_MODEL_MAP["RZR 1000"]

    else:
        # Rental: vehicle comes from Activity column
        # Phase 1: Try exact dictionary match (handles legacy strict mappings)
        for rental_key, model_key in RENTAL_VEHICLE_MAP.items():
            if rental_key in activity:
                return VEHICLE_MODEL_MAP.get(model_key)

        # Phase 2: Fuzzy Substring Fallback (Prevents bot drift when Polaris alters the name prefix)
        act_lower = activity.lower()
        is_4_seat = any(x in act_lower for x in ["4-seat", "4 seat", "4 passenger"])
        # If not explicitly 4, and Pro S / XPS, fallback to 2-seat by default
        
        if "pro r" in act_lower:
            return VEHICLE_MODEL_MAP.get("Pro R")
        elif "pro s" in act_lower or "pros" in act_lower:
            return VEHICLE_MODEL_MAP.get("PRO S4" if is_4_seat else "Turbo Pro S")
        elif "xp s" in act_lower or "xps" in act_lower:
            return VEHICLE_MODEL_MAP.get("XP S 1000" if is_4_seat else "XP S")
            
        # Absolute fallback if it's a completely unknown vehicle
        return None


def get_mpowr_vehicles_list(activity: str, ticket_parts: list, tt_info: dict) -> list:
    """
    Extracts a list of all vehicles and their quantities from the ticket parts.
    Supports multi-vehicle rental reservations.
    """
    booking_type = determine_booking_type(activity)
    
    # Tours never mix vehicle types
    if booking_type == "tour" or not ticket_parts:
        model = get_mpowr_vehicle(activity, tt_info)
        qty = tt_info.get("vehicle_qty", 1)
        if model:
            return [{"model": model, "qty": qty}]
        return []
        
    # Rentals can have mixed vehicles. Each ticket_part represents a vehicle group.
    vehicles = []
    for part in ticket_parts:
        import re
        # Extract quantity from ticket part
        qty_match = re.search(r'x(\d+)\s*$', part, re.IGNORECASE)
        qty = int(qty_match.group(1)) if qty_match else 1
        
        # Determine vehicle for this specific ticket part
        part_lower = part.lower()
        is_4_seat = any(x in part_lower for x in ["4-seat", "4 seat", "4 passenger"])
        model = None
        
        if "pro r" in part_lower:
            model = VEHICLE_MODEL_MAP.get("Pro R")
        elif "pro s" in part_lower or "pros" in part_lower:
            model = VEHICLE_MODEL_MAP.get("PRO S4" if is_4_seat else "Turbo Pro S")
        elif "xp s" in part_lower or "xps" in part_lower or "1000" in part_lower:
            model = VEHICLE_MODEL_MAP.get("XP S 1000" if is_4_seat else "XP S")
        elif "xpedition" in part_lower or "xp5" in part_lower:
            model = VEHICLE_MODEL_MAP.get("Xpedition")
            
        if not model:
            # Fallback to the main activity string if ticket part didn't specify
            model = get_mpowr_vehicle(activity, tt_info)
            
        if model:
            # Aggregate quantities if we already have this model
            found = False
            for v in vehicles:
                if v["model"] == model:
                    v["qty"] += qty
                    found = True
                    break
            if not found:
                vehicles.append({"model": model, "qty": qty})
                
    return vehicles


def _build_single_payload(row: dict, row_index: int) -> dict:
    """
    Internal helper to build a single reservation payload from a raw Google Sheets row dict.

    Args:
        row: Dict from sheet.get_all_records() with exact column headers
        row_index: The 1-indexed sheet row number (for writeback)

    Returns:
        Dict with all fields needed by MpowrCreatorBot.create_reservation()
        Returns {"error": "reason"} if critical data is missing
    """
    activity = str(row.get("Activity", "")).strip()
    ticket_type = str(row.get("Ticket Type", "")).strip()
    tw_confirmation = str(row.get("TW Confirmation", "")).strip()

    first_name_lower = str(row.get("First Name", "")).strip().lower()
    last_name_lower = str(row.get("Last Name", "")).strip().lower()

    if "test" in first_name_lower or "test" in last_name_lower:
        return {"error": "Skipped: Test reservation"}

    if not activity:
        return {"error": "Missing Activity column"}
    if not tw_confirmation:
        return {"error": "Missing TW Confirmation"}
        
    act_lower = activity.lower()
    tt_lower = ticket_type.lower()
        
    if "tripadvisor exclusive" in act_lower:
        return {"error": "Skipped: TripAdvisor Exclusive activities are managed natively"}
    
    if "pro xperience" in act_lower:
        return {"error": "Skipped: Pro XPerience activities do not require MPOWR reservations"}
        
    has_guide_rider = any(kw in act_lower or kw in tt_lower for kw in ["guide car passenger", "guide car rider"])
    has_vehicle = any(kw in tt_lower for kw in ["rzr", "pro r", "turbo", "xpedition", "xp5", "driver", "xp s", "1000", "hour", "day"])
    
    if has_guide_rider and not has_vehicle:
        return {"error": "Skipped: Guide Car Passenger/Rider only (No MPOWR inventory required)"}

    booking_type = determine_booking_type(activity)
    tt_info = parse_ticket_type(ticket_type, activity)

    mpowr_activity = get_mpowr_activity(activity, tt_info)
    if not mpowr_activity:
        return {"error": f"Cannot map activity '{activity}' to MPOWR. Ticket Type was: '{ticket_type}'"}

    mpowr_vehicle = get_mpowr_vehicle(activity, tt_info)
    if not mpowr_vehicle:
        return {"error": f"Cannot map vehicle for activity '{activity}', ticket type '{ticket_type}'"}

    # Guide add-ons (tours only) — returns a LIST for mixed-config support
    guide_addons = GuideAddonSelector.get_guide_selections(
        activity=activity,
        vehicle_model=tt_info.get("model", ""),
        guide_breakdown=tt_info.get("guide_breakdown", []),
        vehicle_qty=tt_info.get("vehicle_qty", 1),
    )

    # Insurance
    has_adventure_assure = row.get("has_adventure_assure", False)
    insurance_choice = "paid" if has_adventure_assure else "free"
    insurance = InsuranceSelector.get_insurance_selection(booking_type, insurance_choice)

    # Price from Sub-Total
    target_price = parse_subtotal(row.get("Sub-Total", 0))

    return {
        "first_name": str(row.get("First Name", "")).strip(),
        "last_name": str(row.get("Last Name", "")).strip(),
        "webhook_email": build_webhook_email(tw_confirmation),
        "phone": str(row.get("Phone", "")).strip(),
        "tw_confirmation": tw_confirmation,
        "activity": activity,
        "booking_type": booking_type,
        "mpowr_activity": mpowr_activity,
        "mpowr_vehicle": mpowr_vehicle,
        "vehicle_qty": tt_info.get("vehicle_qty", 1),
        "rider_config": tt_info.get("rider_config"),
        "activity_date": str(row.get("Activity Date", "")).strip().split(" ")[0],  # BUG-4: Strip time portion
        "normalized_date": str(row.get("Normalized Date", "")).strip(),
        "activity_time": str(row.get("Activity Time", "")).strip(),
        "guide_addons": guide_addons,  # LIST of guide dicts (supports mixed configs)
        "insurance_label": insurance,
        "target_price": target_price,
        "sheet_row_index": row_index,
        "ticket_duration_string": str(tt_info.get("duration", "")),
        "error": None,
    }

def build_customer_payloads_from_row(row: dict, row_index: int) -> list[dict]:
    """
    Returns a list of payloads for MPOWR creation.
    If a rental row has multiple ticket types/vehicles separated by commas, it is now
    automatically grouped into a single unified reservation with a >1 vehicle quantity.
    """
    return [_build_single_payload(row, row_index)]


def build_payloads_from_webhook(webhook_json: dict) -> list[dict]:
    """
    Webhook-First Architecture: Builds a list of reservation payloads directly from
    TripWorks webhook JSON, bypassing the Zapier Google Sheet entirely.
    
    This handles MIXED bookings by iterating over all tripOrders.
    
    Args:
        webhook_json: The raw _payload dict from the webhook sniffer
        
    Returns:
        List of Dicts matching the same format as _build_single_payload() output.
        If an order has an error, its dict will be {"error": "reason"}.
    """
    from datetime import datetime
    
    # Extract core fields
    payload = webhook_json.get("_payload", webhook_json)
    tw_conf = str(payload.get("confirmation_code", "")).strip()
    if not tw_conf:
        return [{"error": "Missing confirmation_code in webhook"}]
    
    customer = payload.get("customer", {})
    first_name = str(customer.get("first_name", "")).strip()
    last_name = str(customer.get("last_name", "")).strip()
    phone = str(customer.get("phone_format_intl", customer.get("phone", ""))).strip()
    
    if not first_name or not last_name:
        return [{"error": f"Missing customer name in webhook for {tw_conf}"}]
    
    # Skip test reservations
    if "test" in first_name.lower() or "test" in last_name.lower():
        return [{"error": "Skipped: Test reservation"}]
    
    trip_orders = payload.get("tripOrders", [])
    if not trip_orders:
        return [{"error": "No tripOrders in webhook"}]
        
    results = []
    
    for order in trip_orders:
        experience = order.get("experience", {})
        activity = experience.get("name", "")
        
        if not activity:
            results.append({"error": f"Missing experience name in webhook for {tw_conf}"})
            continue
    
        act_lower = activity.lower()
        
        # Skip non-MPOWR activities
        if "tripadvisor exclusive" in act_lower:
            results.append({"error": "Skipped: TripAdvisor Exclusive activities are managed natively"})
            continue
        if "pro xperience" in act_lower:
            results.append({"error": "Skipped: Pro XPerience activities do not require MPOWR reservations"})
            continue
            
        # Extract ticket type from non-waiver bookings
        bookings = order.get("bookings", [])
        ticket_parts = []
        has_guide_rider = False
        has_vehicle_ticket = False
        
        for b in bookings:
            ect_name = str(b.get("experience_customer_type", {}).get("name", "")).strip()
            if ect_name and ect_name != "Guest Waiver":
                ticket_parts.append(ect_name)
                ect_lower = ect_name.lower()
                if any(kw in ect_lower for kw in ["guide car passenger", "guide car rider"]):
                    has_guide_rider = True
                if any(kw in ect_lower for kw in ["rzr", "pro r", "turbo", "xpedition", "xp", "1000", "hour", "day", "seat", "driver"]):
                    has_vehicle_ticket = True
        
        # Also check activity name for guide car
        if "guide car passenger" in act_lower or "guide car rider" in act_lower:
            has_guide_rider = True
        
        if has_guide_rider and not has_vehicle_ticket:
            results.append({"error": "Skipped: Guide Car Passenger/Rider only (No MPOWR inventory required)"})
            continue
            
        ticket_type_str = ", ".join(ticket_parts) if ticket_parts else ""
        
        # Determine booking type and parse ticket info
        booking_type = determine_booking_type(activity)
        tt_info = parse_ticket_type(ticket_type_str, activity)
        
        mpowr_activity = get_mpowr_activity(activity, tt_info)
        if not mpowr_activity:
            results.append({"error": f"Cannot map activity '{activity}' to MPOWR. Ticket Type was: '{ticket_type_str}'"})
            continue
            
        vehicles_list = get_mpowr_vehicles_list(activity, ticket_parts, tt_info)
        if not vehicles_list:
            results.append({"error": f"Cannot map vehicle for activity '{activity}', ticket type '{ticket_type_str}'"})
            continue
            
        # Backwards compatibility
        mpowr_vehicle = vehicles_list[0]["model"]
        
        # Date/Time from experience_timeslot (clean ISO format — no serial time issues)
        timeslot = order.get("experience_timeslot", {})
        start_time_str = timeslot.get("start_time", "")
        end_time_str = timeslot.get("end_time", "")
        time_label = timeslot.get("label", "")  # e.g., "3:30 PM" — already formatted
        
        def _strip_tz(dt_str):
            """Strip timezone offset from ISO datetime to get naive local time."""
            import re
            return re.sub(r'[+-]\d{2}:\d{2}$', '', dt_str.replace('Z', ''))
            
        if start_time_str:
            start_dt = datetime.fromisoformat(_strip_tz(start_time_str))
            activity_date = start_dt.strftime("%m/%d/%Y")
            activity_time = time_label or start_dt.strftime("%I:%M %p").lstrip("0")
            
            # FIX for Multi-Day Bookings: compute duration if missing
            if end_time_str and booking_type == "rental" and not tt_info.get("duration"):
                end_dt = datetime.fromisoformat(_strip_tz(end_time_str))
                hours = round((end_dt - start_dt).total_seconds() / 3600)
                if hours <= 3:
                    tt_info["duration"] = "3 Hour"
                elif hours <= 5:
                    tt_info["duration"] = "Half-Day"
                elif hours <= 10:
                    tt_info["duration"] = "Full-Day"
                elif hours <= 24:
                    tt_info["duration"] = "24 Hour"
                else:
                    tt_info["duration"] = "Multi-Day"
                    
        else:
            # Fallback to sale_date
            sale_date = payload.get("sale_date", "")
            if sale_date:
                start_dt = datetime.fromisoformat(_strip_tz(sale_date))
                activity_date = start_dt.strftime("%m/%d/%Y")
            else:
                activity_date = ""
            activity_time = time_label or ""
            
        # Price (webhook gives cents — clean conversion, no ambiguity)
        subtotal_cents = payload.get("subtotal", 0)
        
        # Insurance & TripSafe deduction
        has_adventure_assure = False
        tripsafe_deduction_cents = 0
        has_tripsafe = False
        for b in bookings:
            for addon in b.get("addons", []):
                addon_name = str(addon.get("name", ""))
                # Must contain "Adventure Assure" but NOT start with "No" (decline option)
                if "Adventure Assure" in addon_name and "No" not in addon_name:
                    if addon.get("price", 0) > 0:
                        has_adventure_assure = True
                        
                # Deduct TripSafe (TripWorks insurance) from the MPOWR target price
                if "tripsafe" in addon_name.lower() or "trip safe" in addon_name.lower() or "protection" in addon_name.lower():
                    if "adventure" not in addon_name.lower() and "no" not in addon_name.lower(): # don't deduct our own assure
                        has_tripsafe = True
                        if addon.get("price", 0) > 0:
                            tripsafe_deduction_cents += addon.get("price", 0)
        
        if has_tripsafe and tripsafe_deduction_cents == 0:
            # TripWorks hides the TripSafe price as $0. It is calculated as 9% of the base subtotal.
            # subtotal_cents = base_cents * 1.09
            base_cents = round(subtotal_cents / 1.09)
            tripsafe_deduction_cents = subtotal_cents - base_cents
            
        target_price = (subtotal_cents - tripsafe_deduction_cents) / 100.0
        
        insurance_choice = "paid" if has_adventure_assure else "free"
        insurance = InsuranceSelector.get_insurance_selection(booking_type, insurance_choice)
        
        # Guide add-ons (tours only)
        guide_addons = GuideAddonSelector.get_guide_selections(
            activity=activity,
            vehicle_model=tt_info.get("model", ""),
            guide_breakdown=tt_info.get("guide_breakdown", []),
            vehicle_qty=tt_info.get("vehicle_qty", 1),
        )
        
        # Party size from pax_count
        party_size = order.get("pax_count", 1)
        
        # Override with "How many people?" custom field if present
        for cf in payload.get("custom_field_values", []):
            cf_name = cf.get("custom_field", {}).get("internal_name", "")
            if "How many people" in cf_name:
                val = cf.get("string_value") or cf.get("text_value") or cf.get("integer_value")
                if val:
                    try:
                        parsed_val = int(str(val).strip())
                        if parsed_val > 0:
                            party_size = parsed_val
                    except ValueError:
                        pass
        
        results.append({
            "first_name": first_name,
            "last_name": last_name,
            "webhook_email": build_webhook_email(tw_conf),
            "phone": phone,
            "tw_confirmation": tw_conf,
            "activity": activity,
            "booking_type": booking_type,
            "mpowr_activity": mpowr_activity,
            "mpowr_vehicle": mpowr_vehicle,
            "vehicles": vehicles_list,
            "vehicle_qty": tt_info.get("vehicle_qty", 1),
            "rider_config": tt_info.get("rider_config"),
            "activity_date": activity_date,
            "normalized_date": activity_date,  # Same since we derive from clean ISO
            "activity_time": activity_time,
            "guide_addons": guide_addons,
            "insurance_label": insurance,
            "target_price": target_price,
            "sheet_row_index": 0,  # No sheet row — webhook-first
            "ticket_duration_string": str(tt_info.get("duration", "")),
            "party_size": party_size,
            "waivers_expected": party_size,
            "waivers_complete": sum(1 for b in bookings if str(b.get("experience_customer_type", {}).get("name", "")).strip() == "Guest Waiver"),
            "_webhook_payload": payload,  # Preserve raw payload for Dashboard push
            "has_tripsafe": has_tripsafe,
            "error": None,
        })
        
    # Group results by identical reservation parameters to combine multi-vehicle bookings
    grouped_results = {}
    for r in results:
        if r.get("error"):
            # Keep errors separate using object ID as a unique dictionary key
            grouped_results[id(r)] = r
            continue
            
        group_key = (r["tw_confirmation"], r["activity_date"], r["activity_time"], r["mpowr_activity"])
        if group_key not in grouped_results:
            grouped_results[group_key] = r
        else:
            existing = grouped_results[group_key]
            
            # Merge vehicles array
            for new_v in r.get("vehicles", []):
                found = False
                for ex_v in existing.get("vehicles", []):
                    if ex_v["model"] == new_v["model"]:
                        ex_v["qty"] += new_v["qty"]
                        found = True
                        break
                if not found:
                    existing["vehicles"].append(new_v)
            
            # Merge target price and counts
            existing["target_price"] += r.get("target_price", 0)
            existing["party_size"] += r.get("party_size", 0)
            existing["waivers_expected"] += r.get("waivers_expected", 0)
            existing["waivers_complete"] += r.get("waivers_complete", 0)
            
            # Combine guide addons if any exist (though usually rentals don't have them)
            existing_addons = {g["label"]: g for g in existing.get("guide_addons", [])}
            for g in r.get("guide_addons", []):
                if g["label"] in existing_addons:
                    existing_addons[g["label"]]["quantity"] += g["quantity"]
                else:
                    existing["guide_addons"].append(g)

    return list(grouped_results.values())


# =============================================================================
# DASHBOARD INTERFACE
# =============================================================================

def map_legacy_to_dashboard(row: dict, mpwr_conf_number: str, webhook_payload: dict) -> dict:
    """
    Translates the legacy Zapier row + Webhook JSON into the strict 47-column Dashboard format.
    """
    from datetime import datetime

    # Base payload processing
    order_id = str(webhook_payload.get("id", row.get("TW Order ID", "")))
    trip_method = webhook_payload.get("trip_method", {}).get("name", "")
    
    sub_total = float(webhook_payload.get("subtotal", 0)) / 100.0 if "subtotal" in webhook_payload else row.get("Sub-Total", 0)
    total = float(webhook_payload.get("total", 0)) / 100.0 if "total" in webhook_payload else row.get("Total", 0)
    amount_paid = float(webhook_payload.get("paid", 0)) / 100.0 if "paid" in webhook_payload else 0
    amount_due = float(webhook_payload.get("due", 0)) / 100.0 if "due" in webhook_payload else 0

    aas_status = "Premium Adventure Assure" if row.get("has_adventure_assure") else "None"

    # Use existing MPOWR mapping string building natively
    payload = _build_single_payload(row, 0)

    # BUG-4 FIX: If the payload builder returns an error (e.g. TripAdvisor Exclusive,
    # Guide Car Passenger), fall back to raw row data instead of using garbage values.
    if payload.get("error"):
        payload = {
            "first_name": str(row.get("First Name", "")).strip(),
            "last_name": str(row.get("Last Name", "")).strip(),
            "phone": str(row.get("Phone", "")).strip(),
            "booking_type": determine_booking_type(str(row.get("Activity", ""))),
            "mpowr_activity": "",
            "mpowr_vehicle": "",
            "vehicle_qty": 1,
            "activity_date": str(row.get("Activity Date", "")).strip().split(" ")[0],
            "normalized_date": str(row.get("Normalized Date", "")).strip(),
            "activity_time": str(row.get("Activity Time", "")).strip(),
            "webhook_email": "",
            "error": None,
        }

    party_size = str(row.get("Party Size", "1"))
    booking_type = payload.get("booking_type", "")
    is_rental = booking_type.lower() == "rental"
    
    # Safely extract TripWorks Notes
    tw_notes = str(row.get("Notes", ""))
    for field in webhook_payload.get("custom_field_values", []):
        field_name = str(field.get("custom_field", {}).get("internal_name", "")).lower()
        if "notes" in field_name:
            extracted = field.get("string_value") or field.get("text_value") or str(field.get("value", ""))
            if extracted and extracted.strip():
                if tw_notes:
                    tw_notes += " | " + extracted.strip()
                else:
                    tw_notes = extracted.strip()
    
    # Safely extract end time
    end_time = ""
    trip_orders = webhook_payload.get("trip_orders", [])
    if trip_orders:
        ts = trip_orders[0].get("experience_timeslot", {})
        if ts.get("end_time"):
            end_time = ts["end_time"]
            # basic clean up: 17:00:00 -> 17:00
            if len(end_time.split(":")) == 3:
                end_time = ":".join(end_time.split(":")[:2])
    
    dashboard_row = {
        "TW Confirmation": str(row.get("TW Confirmation", "")),
        "TW Order ID": order_id,
        "First Name": payload.get("first_name", ""),
        "Last Name": payload.get("last_name", ""),
        "Email": str(row.get("Email", "")),
        "Phone": payload.get("phone", ""),
        
        "Activity": str(row.get("Activity", "")),
        "Activity Internal": payload.get("mpowr_activity", ""),
        "Booking Type": booking_type,
        "Ticket Type": str(row.get("Ticket Type", "")),
        
        "Vehicle Model": payload.get("mpowr_vehicle", ""),
        "Vehicle Qty": payload.get("vehicle_qty", 1),
        "Party Size": party_size,
        
        "Activity Date": payload.get("activity_date", ""),
        "Activity Time": payload.get("activity_time", ""),
        "End Time": end_time, 
        "Normalized Date": payload.get("normalized_date", ""),
        "Rental Return Time": end_time,  # V2: Populated post-creation or from End Time
        
        "Sub-Total": sub_total,
        "Total": total,
        "Amount Paid": amount_paid,
        "Amount Due": amount_due,
        
        "Adventure Assure": aas_status,
        "Trip Safe": "Purchased" if row.get("has_tripsafe") else "Declined",
        "Deposit Status": "Due" if amount_due > 0 else "Collected",
        "Payment Collected By": "",
        "Payment Notes": "",
        
        "MPWR Confirmation Number": mpwr_conf_number,
        "MPWR Waiver Link": "",  # Populated by standalone Waiver Link Scraper after creation
        "MPWR Status": "Created" if mpwr_conf_number else "Error",
        "Webhook Email": payload.get("webhook_email", ""),
        "Primary Rider": f"{payload.get('first_name', '')} {payload.get('last_name', '')}".strip(),
        
        "Epic Waivers Expected": party_size,
        "Epic Waivers Complete": payload.get("waivers_complete", 0),
        "Epic Waiver Names": "",
        
        "Polaris Waivers Expected": party_size,
        "Polaris Waivers Complete": 0,
        "Polaris Waiver Names": "",
        
        "OHV Required": "TRUE" if is_rental else "FALSE",
        "OHV Permits Expected": str(payload.get("vehicle_qty", 1)) if is_rental else "0",
        "OHV Permits Uploaded": "0",
        "OHV Permit Names": "",
        "OHV Uploaded": "FALSE",
        "OHV File Path": "",
        "Rental Status": "",
        
        "Checked In": "FALSE",
        "Checked In At": "",
        "Checked In By": "",
        
        "TW Booking Link": f"https://epic4x4.tripworks.com/trip/{row.get('TW Confirmation', '')}/bookings",
        "Customer Portal Link": f"https://www.epicreservation.com/portal/{row.get('TW Confirmation', '')}",
        "Trip Method": trip_method,
        "Notes": tw_notes,
        
        "Created At": datetime.now().isoformat(),
        "Last Updated": datetime.now().isoformat(),
    }
    
    return dashboard_row
def extract_update_data(payload: dict) -> dict:
    """
    Extracts relevant update fields from a TripWorks webhook payload
    and formats them for both Supabase and MPOWR updater bot.
    """
    payloads = build_payloads_from_webhook({"_payload": payload})
    if not payloads or payloads[0].get("error"):
        return {"error": payloads[0].get("error") if payloads else "No payload generated"}
        
    p = payloads[0] # primary payload
    
    total_vehicles = sum(x.get("vehicle_qty", 1) for x in payloads)
    
    from datetime import datetime, timedelta
    try:
        date_obj = datetime.strptime(p["activity_date"], "%m/%d/%Y")
    except ValueError:
        date_obj = datetime.now()
        
    end_date_obj = date_obj
    activity_lower = p["mpowr_activity"].lower()
    time_raw_lower = p["activity_time"].lower()
    duration_lower = p.get("duration", "").lower()
    
    # Check if this is a multi-day rental to calculate the end date
    multi_day_match = re.search(r'(\d+)-day', activity_lower + " " + time_raw_lower + " " + duration_lower)
    if multi_day_match:
        days = int(multi_day_match.group(1))
        if days > 1:
            end_date_obj = date_obj + timedelta(days=days - 1)
    
    bot_payload = {
        "activity": p["mpowr_activity"],
        "start_date_obj": date_obj,
        "end_date_obj": end_date_obj,
        "time_raw": p["activity_time"],
        "vehicles": p.get("vehicles", [{"model": p["mpowr_vehicle"], "qty": p["vehicle_qty"]}]),
        "guide_addons": p.get("guide_addons", []),
        "subtotal": f"{p['target_price']:.2f}",
        "customer_name": f"{p['first_name']} {p['last_name']}",
        "mpowr_vehicle": p["mpowr_vehicle"]
    }
    
    raw_supabase_updates = {
        "first_name": p["first_name"],
        "last_name": p["last_name"],
        "phone": p["phone"],
        "activity": p["activity"],
        "activity_date": p["activity_date"],
        "activity_time": p["activity_time"],
        "vehicle_model": p["mpowr_vehicle"],
        "vehicle_qty": total_vehicles,
        "party_size": p["party_size"],
        "sub_total": p["target_price"],
        "total": p["target_price"],
        "epic_waivers_expected": p["waivers_expected"],
        "polaris_waivers_expected": p["waivers_expected"],
    }
    
    # Safe Merge: Strip out empty strings or None so we don't overwrite valid legacy Zapier data
    supabase_updates = {k: v for k, v in raw_supabase_updates.items() if v != "" and v is not None and v != [] and v != {}}
    
    return {
        "mpowr_payload": bot_payload,
        "supabase_updates": supabase_updates,
        "error": None
    }

