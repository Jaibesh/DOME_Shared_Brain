import pytest
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data_mapper import GuideAddonSelector

def test_guide_selector_rentals():
    # Rentals get no guide
    assert GuideAddonSelector.get_guide_selection(
        "2026 2-Seat RZR Pro R Ultimate", "Pro R", "1-2", 1
    ) is None

def test_guide_selector_hells_revenge():
    # Hells Revenge + RZR 1000 + 1-2 People
    res1 = GuideAddonSelector.get_guide_selection(
        "Gateway to Hell's Revenge and Fins N' Things", "RZR 1000", "1-2", 2
    )
    assert res1["label"] == GuideAddonSelector.HELLS_REVENGE_GUIDES["1-2"]
    assert res1["quantity"] == 2

    # Hells Revenge + RZR 1000 + 3-4 People
    res2 = GuideAddonSelector.get_guide_selection(
        "Gateway to Hell's Revenge and Fins N' Things", "RZR 1000", "3-4", 1
    )
    assert res2["label"] == GuideAddonSelector.HELLS_REVENGE_GUIDES["3-4"]
    assert res2["quantity"] == 1

    # Hells Revenge + Pro R -> always Pro R guide
    res3 = GuideAddonSelector.get_guide_selection(
        "Hell's Revenge - Pro R Ultimate Experience", "Pro R", "1-2", 3
    )
    assert res3["label"] == GuideAddonSelector.HELLS_REVENGE_GUIDES["Pro R"]
    assert res3["quantity"] == 3

def test_guide_selector_poison_spider():
    res = GuideAddonSelector.get_guide_selection(
        "Poison Spider Mesa Tour", "Pro R", "1-2", 2
    )
    assert res["label"] == GuideAddonSelector.POISON_SPIDER_GUIDE
    assert res["quantity"] == 2

def test_guide_selector_discovery():
    res = GuideAddonSelector.get_guide_selection(
        "Moab Discovery Tour", "Xpedition", "1-2", 1
    )
    assert res["label"] == GuideAddonSelector.DISCOVERY_GUIDE
    assert res["quantity"] == 1
