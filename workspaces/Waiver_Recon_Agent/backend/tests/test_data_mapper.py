import pytest
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data_mapper import parse_ticket_type, parse_subtotal, select_best_time_slot, build_webhook_email


def test_build_webhook_email():
    assert build_webhook_email("CO-D5A-8KY") == "polaris+CO-D5A-8KY@epic4x4adventures.com"
    assert build_webhook_email(" CO-123-456 ") == "polaris+CO-123-456@epic4x4adventures.com"


def test_parse_subtotal():
    assert parse_subtotal("185500") == 1855.00
    assert parse_subtotal(185500) == 1855.00
    assert parse_subtotal("1855.00") == 1855.00
    assert parse_subtotal(1855.00) == 1855.00
    assert parse_subtotal("$1,855.00") == 1855.00
    assert parse_subtotal("1855") == 1855.0  # Assumes small integer without 00 is dollars or it falls into ambiguous case but returns correctly
    assert parse_subtotal(15000) == 150.0  # Ambiguous case without decimal, but ends in 00 and >= 10000 => cents
    assert parse_subtotal(950) == 950.0  # < 10000, returns as is
    assert parse_subtotal("") == 0.0


def test_select_best_time_slot():
    available = ["4:00 PM", "4:30 PM", "5:00 PM", "5:30 PM"]
    assert select_best_time_slot(available, "5:15 PM") == "5:00 PM"
    assert select_best_time_slot(available, "5:00 PM") == "5:00 PM"
    assert select_best_time_slot(available, "3:00 PM") is None
    
    available_am = ["8:00 AM", "8:30 AM", "9:00 AM"]
    assert select_best_time_slot(available_am, "8:45 AM") == "8:30 AM"
    assert select_best_time_slot(available_am, "9:00 AM") == "9:00 AM"


def test_parse_ticket_type_tours():
    # Tour 1
    tt1 = "2026 RZR 1000 for 1 - 2 People x3, Guest Waiver x2"
    act1 = "Gateway to Hell's Revenge and Fins N' Things"
    res1 = parse_ticket_type(tt1, act1)
    assert res1["model"] == "RZR 1000"
    assert res1["rider_config"] == "1-2"
    assert res1["vehicle_qty"] == 3
    assert res1["duration"] is None

    # Tour 2: Pro R
    tt2 = "2026 RZR Pro R for 1 - 2 People x1"
    act2 = "Hell's Revenge - Pro R Ultimate Experience"
    res2 = parse_ticket_type(tt2, act2)
    assert res2["model"] == "Pro R"  # Gets overridden to Pro R by activity logic too
    assert res2["vehicle_qty"] == 1


def test_parse_ticket_type_rentals():
    # Rental 1
    tt1 = "Half-Day Up to 5 Hours x2"
    act1 = "2026 4-Seat Polaris RZR XP S 1000 Ultimate"
    res1 = parse_ticket_type(tt1, act1)
    assert res1["model"] is None  # Rental model is parsed separately from activity later
    assert res1["duration"] == "Half-Day Up to 5 Hours"
    assert res1["vehicle_qty"] == 2

    # Rental 2
    tt2 = "3-Day Rental x1"
    act2 = "2026 2-Seat RZR Pro R Ultimate"
    res2 = parse_ticket_type(tt2, act2)
    assert res2["duration"] == "3-Day Rental"
    assert res2["vehicle_qty"] == 1
