"""
DOME Framework - Estimating Engine
Calculates job estimates for Beh Brothers Electric.
Dynamically loads prices from price_book.csv.
"""

import os
import csv
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Business defaults (can be overridden by .env)
LABOR_RATE = float(os.getenv('LABOR_RATE', 125.00))
PARTS_MARKUP = float(os.getenv('PARTS_MARKUP_PERCENT', 30)) / 100

# Price book location
PRICE_BOOK_PATH = Path(__file__).parent.parent / "brain" / "sources" / "price_book.csv"

# =============================================================================
# PRICE BOOK LOADING
# =============================================================================

_price_book_cache = None
_price_book_mtime = None


def _load_price_book() -> Dict[str, Dict]:
    """Load price book from CSV with caching."""
    global _price_book_cache, _price_book_mtime
    
    if not PRICE_BOOK_PATH.exists():
        return {}
    
    # Check if file has been modified
    current_mtime = PRICE_BOOK_PATH.stat().st_mtime
    if _price_book_cache is not None and _price_book_mtime == current_mtime:
        return _price_book_cache
    
    price_book = {}
    try:
        with open(PRICE_BOOK_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                item_name = row.get('Item Name', '').strip()
                # Skip section header comments (# ====) but not wire gauges like #4 Bare Copper
                if not item_name or (item_name.startswith('# ') and '=' in item_name):
                    continue
                
                try:
                    cost = float(row.get('Cost') or 0)
                    price = float(row.get('Price') or 0)
                except (ValueError, TypeError):
                    cost = 0.0
                    price = 0.0
                
                price_book[item_name] = {
                    'name': item_name,
                    'category': row.get('Category', ''),
                    'sku': row.get('SKU', ''),
                    'cost': cost,
                    'price': price,
                    'unit': row.get('Unit', 'each'),
                    'description': row.get('Description', '')
                }
        
        _price_book_cache = price_book
        _price_book_mtime = current_mtime
    except Exception as e:
        print(f"Warning: Could not load price book: {e}")
    
    return price_book


def get_part_cost(item_name: str) -> float:
    """Get part cost from price book (before markup)."""
    price_book = _load_price_book()
    
    # Exact match
    if item_name in price_book:
        return price_book[item_name]['cost']
    
    # Case-insensitive partial match
    item_lower = item_name.lower()
    for name, details in price_book.items():
        if item_lower in name.lower() or name.lower() in item_lower:
            return details['cost']
    
    return 0.0


def get_part_price(item_name: str) -> float:
    """Get part price from price book (with markup)."""
    price_book = _load_price_book()
    
    if item_name in price_book:
        return price_book[item_name]['price']
    
    item_lower = item_name.lower()
    for name, details in price_book.items():
        if item_lower in name.lower() or name.lower() in item_lower:
            return details['price']
    
    return 0.0


# =============================================================================
# JOB TEMPLATES (Reference price book for actual costs)
# =============================================================================

def _get_template_parts(parts_config: List[Dict]) -> List[Dict]:
    """Resolve parts from price book with fallback to provided costs."""
    resolved = []
    for p in parts_config:
        item = p['item']
        qty = p['qty']
        cost = get_part_cost(item)
        
        # Fallback to provided cost if not in price book
        if cost == 0 and 'cost' in p:
            cost = p['cost']
        
        resolved.append({
            'item': item,
            'qty': qty,
            'cost': cost
        })
    
    return resolved


JOB_TEMPLATES = {
    "200a_overhead_service": {
        "name": "200A Overhead Service Upgrade",
        "base_men": 2,
        "base_hours": 8,
        "parts_config": [
            {"item": "200A Meter Socket (Ringless)", "qty": 1},
            {"item": "200A Main Breaker Panel 30-Space", "qty": 1},
            {"item": "4/0 Aluminum SE Cable (Triplex)", "qty": 40},
            {"item": "2\" Rigid Mast Kit", "qty": 1},
            {"item": "Ground Rod (8ft Copper Clad)", "qty": 2},
            {"item": "#4 Bare Copper (GEC)", "qty": 50},
            {"item": "Service Wedge Clamp", "qty": 2},
            {"item": "Intersystem Bonding Bridge", "qty": 1},
            {"item": "Ground Rod Clamp (Acorn)", "qty": 2},
        ]
    },
    "200a_underground_service": {
        "name": "200A Underground Service Upgrade",
        "base_men": 2,
        "base_hours": 6,
        "parts_config": [
            {"item": "200A Meter Socket (Side Bus)", "qty": 1},
            {"item": "200A Main Breaker Panel 30-Space", "qty": 1},
            {"item": "2\" PVC Expansion Joint", "qty": 1},
            {"item": "2\" Schedule 80 PVC (10ft)", "qty": 2},
            {"item": "Ground Rod (8ft Copper Clad)", "qty": 2},
            {"item": "#4 Bare Copper (GEC)", "qty": 50},
            {"item": "Intersystem Bonding Bridge", "qty": 1},
            {"item": "Ground Rod Clamp (Acorn)", "qty": 2},
        ]
    },
    "100a_service_upgrade": {
        "name": "100A Service Upgrade",
        "base_men": 2,
        "base_hours": 6,
        "parts_config": [
            {"item": "100A Meter Socket", "qty": 1},
            {"item": "100A Main Breaker Panel", "qty": 1},
            {"item": "2/0 Aluminum SE Cable", "qty": 30},
            {"item": "2\" Rigid Mast Kit", "qty": 1},
            {"item": "Ground Rod (8ft Copper Clad)", "qty": 2},
            {"item": "#6 Bare Copper (GEC)", "qty": 40},
            {"item": "Ground Rod Clamp (Acorn)", "qty": 2},
        ]
    },
    "subpanel_installation": {
        "name": "Subpanel Installation",
        "base_men": 1,
        "base_hours": 4,
        "parts_config": [
            {"item": "100A Subpanel", "qty": 1},
            {"item": "60A Double Pole BR", "qty": 1},
            {"item": "6 AWG Copper THHN", "qty": 100},
            {"item": "1\" EMT (10ft)", "qty": 3},
            {"item": "EMT Connector 1\"", "qty": 6},
        ]
    },
    "ev_charger_installation": {
        "name": "EV Charger Installation (Level 2)",
        "base_men": 1,
        "base_hours": 4,
        "parts_config": [
            {"item": "NEMA 14-50 Receptacle", "qty": 1},
            {"item": "NEMA 14-50 Surface Mount Box", "qty": 1},
            {"item": "50A GFCI Breaker", "qty": 1},
            {"item": "6/3 NM-B Romex", "qty": 50},
        ]
    },
    "ev_charger_long_run": {
        "name": "EV Charger (Long Run/Conduit)",
        "base_men": 2,
        "base_hours": 6,
        "parts_config": [
            {"item": "NEMA 14-50 Receptacle", "qty": 1},
            {"item": "NEMA 14-50 Surface Mount Box", "qty": 1},
            {"item": "50A GFCI Breaker", "qty": 1},
            {"item": "6 AWG Copper THHN", "qty": 200},
            {"item": "1\" EMT (10ft)", "qty": 10},
            {"item": "EMT Connector 1\"", "qty": 12},
        ]
    },
    "recessed_lighting": {
        "name": "Recessed Lighting Installation",
        "base_men": 1,
        "base_hours_per_unit": 0.5,
        "parts_per_unit_config": [
            {"item": "6\" LED Wafer Light", "qty": 1},
        ]
    },
    "recessed_lighting_new_construction": {
        "name": "Recessed Lighting (New Construction)",
        "base_men": 1,
        "base_hours_per_unit": 0.75,
        "parts_per_unit_config": [
            {"item": "6\" Recessed Housing (New Work)", "qty": 1},
            {"item": "6\" LED Wafer Light", "qty": 1},
            {"item": "14/2 NM-B Romex", "qty": 15},
        ]
    },
    "ceiling_fan_installation": {
        "name": "Ceiling Fan Installation",
        "base_men": 1,
        "base_hours": 1.5,
        "parts_config": [
            {"item": "Ceiling Fan Box (Remodel)", "qty": 1},
            {"item": "Fan/Light Wall Switch", "qty": 1},
            {"item": "Push-In Connectors 3-Port", "qty": 4},
        ]
    },
    "ceiling_fan_with_switch": {
        "name": "Ceiling Fan + New Switch Run",
        "base_men": 1,
        "base_hours": 3,
        "parts_config": [
            {"item": "Ceiling Fan Box (Remodel)", "qty": 1},
            {"item": "Fan Speed Control", "qty": 1},
            {"item": "Single Gang Box (Old Work)", "qty": 1},
            {"item": "14/2 NM-B Romex", "qty": 40},
            {"item": "Push-In Connectors 3-Port", "qty": 6},
        ]
    },
    "outlet_installation": {
        "name": "Outlet Installation",
        "base_men": 1,
        "base_hours": 1,
        "parts_config": [
            {"item": "Duplex Outlet (15A) White", "qty": 1},
            {"item": "Single Gang Box (Old Work)", "qty": 1},
            {"item": "Outlet Cover Plate (White)", "qty": 1},
            {"item": "14/2 NM-B Romex", "qty": 25},
        ]
    },
    "gfci_outlet_installation": {
        "name": "GFCI Outlet Installation",
        "base_men": 1,
        "base_hours": 1,
        "parts_config": [
            {"item": "GFCI Outlet (20A)", "qty": 1},
            {"item": "Single Gang Box (Old Work)", "qty": 1},
            {"item": "Outlet Cover Plate (White)", "qty": 1},
            {"item": "12/2 NM-B Romex", "qty": 25},
        ]
    },
    "dedicated_circuit_20a": {
        "name": "Dedicated 20A Circuit",
        "base_men": 1,
        "base_hours": 2,
        "parts_config": [
            {"item": "Duplex Outlet (20A)", "qty": 1},
            {"item": "Single Gang Box (Old Work)", "qty": 1},
            {"item": "20A Single Pole BR", "qty": 1},
            {"item": "Outlet Cover Plate (White)", "qty": 1},
            {"item": "12/2 NM-B Romex", "qty": 50},
        ]
    },
    "surge_protector_installation": {
        "name": "Whole House Surge Protector",
        "base_men": 1,
        "base_hours": 1.5,
        "parts_config": [
            {"item": "Surge Protector (Standard)", "qty": 1},
            {"item": "30A Double Pole BR", "qty": 1},
        ]
    },
    "smoke_detector_installation": {
        "name": "Smoke/CO Detector Installation",
        "base_men": 1,
        "base_hours_per_unit": 0.5,
        "parts_per_unit_config": [
            {"item": "Smoke/CO Combo (Hardwired)", "qty": 1},
            {"item": "Single Gang Box (Old Work)", "qty": 1},
            {"item": "14/2 NM-B Romex", "qty": 20},
        ]
    },
    "troubleshooting": {
        "name": "Electrical Troubleshooting",
        "base_men": 1,
        "base_hours": 2,
        "parts_config": []
    },
    "panel_inspection": {
        "name": "Electrical Panel Inspection",
        "base_men": 1,
        "base_hours": 1,
        "parts_config": []
    },
    "generator_inlet": {
        "name": "Generator Inlet Installation",
        "base_men": 1,
        "base_hours": 3,
        "parts_config": [
            {"item": "Generator Inlet Box (30A)", "qty": 1},
            {"item": "Generator Interlock Kit", "qty": 1},
            {"item": "30A Double Pole BR", "qty": 1},
            {"item": "10/3 NM-B Romex", "qty": 30},
        ]
    },
    "hot_tub_installation": {
        "name": "Hot Tub/Spa Electrical",
        "base_men": 2,
        "base_hours": 4,
        "parts_config": [
            {"item": "Spa Panel (50A)", "qty": 1},
            {"item": "50A Double Pole BR", "qty": 1},
            {"item": "6/3 NM-B Romex", "qty": 40},
        ]
    },
    "hvac_disconnect": {
        "name": "HVAC Disconnect Installation",
        "base_men": 1,
        "base_hours": 2,
        "parts_config": [
            {"item": "Disconnect Box (60A Fused)", "qty": 1},
            {"item": "AC Whip (3/4\" x 6ft)", "qty": 1},
            {"item": "Time Delay Fuse (30A)", "qty": 1},
        ]
    }
}


# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def calculate_labor(men: int, hours: float, rate: float = LABOR_RATE) -> float:
    """
    Calculate labor cost.
    
    Args:
        men: Number of workers
        hours: Hours worked
        rate: Hourly rate per person
        
    Returns:
        Total labor cost
    """
    return men * hours * rate


def calculate_parts_total(
    parts: List[Dict], 
    markup: float = PARTS_MARKUP
) -> Tuple[float, float, float]:
    """
    Calculate parts cost with markup.
    
    Args:
        parts: List of part dicts with 'qty' and 'cost' keys
        markup: Markup percentage as decimal (0.30 = 30%)
        
    Returns:
        Tuple of (base_cost, markup_amount, total_with_markup)
    """
    base_cost = sum(p['qty'] * p['cost'] for p in parts)
    markup_amount = base_cost * markup
    total = base_cost + markup_amount
    return base_cost, markup_amount, total


def generate_estimate(
    job_type: str,
    men: Optional[int] = None,
    hours: Optional[float] = None,
    custom_parts: Optional[List[Dict]] = None,
    quantity: int = 1,
    notes: str = ""
) -> Dict:
    """
    Generate a full job estimate with live pricing from price book.
    
    Args:
        job_type: Key from JOB_TEMPLATES
        men: Override number of workers
        hours: Override hours
        custom_parts: Additional parts to add
        quantity: Number of units (for per-unit jobs like recessed lights)
        notes: Additional notes
        
    Returns:
        Complete estimate dictionary
    """
    # Input validation
    if quantity is not None and quantity < 1:
        return {"error": "Quantity must be at least 1"}
    if men is not None and men < 1:
        return {"error": "Number of workers must be at least 1"}
    if hours is not None and hours <= 0:
        return {"error": "Hours must be positive"}
    
    template = JOB_TEMPLATES.get(job_type)
    if not template:
        return {"error": f"Unknown job type: {job_type}"}
    
    # Determine labor
    actual_men = men or template.get('base_men', 1)
    
    # Handle per-unit jobs (like recessed lighting)
    if 'base_hours_per_unit' in template:
        actual_hours = hours or (template['base_hours_per_unit'] * quantity)
        parts_config = template.get('parts_per_unit_config', [])
        parts = []
        for p in parts_config:
            cost = get_part_cost(p['item'])
            parts.append({
                'item': p['item'],
                'qty': p['qty'] * quantity,
                'cost': cost
            })
    else:
        actual_hours = hours or template.get('base_hours', 1)
        parts_config = template.get('parts_config', [])
        parts = _get_template_parts(parts_config)
    
    # Add custom parts
    if custom_parts:
        for cp in custom_parts:
            item = cp.get('item', cp.get('name', 'Custom Part'))
            qty = cp.get('qty', cp.get('quantity', 1))
            cost = get_part_cost(item)
            if cost == 0 and 'cost' in cp:
                cost = cp['cost']
            parts.append({'item': item, 'qty': qty, 'cost': cost})
    
    # Calculate costs
    labor_cost = calculate_labor(actual_men, actual_hours)
    parts_base, parts_markup, parts_total = calculate_parts_total(parts)
    
    total = labor_cost + parts_total
    
    return {
        "job_name": template['name'],
        "job_type": job_type,
        "created_at": datetime.now().isoformat(),
        "labor": {
            "men": actual_men,
            "hours": actual_hours,
            "rate": LABOR_RATE,
            "total": labor_cost
        },
        "parts": {
            "items": parts,
            "subtotal": parts_base,
            "markup_percent": PARTS_MARKUP * 100,
            "markup_amount": parts_markup,
            "total": parts_total
        },
        "grand_total": total,
        "quantity": quantity,
        "notes": notes
    }



def generate_parts_list(job_type: str, quantity: int = 1) -> List[Dict]:
    """
    Generate a parts list for a specific job type with live pricing.
    
    Args:
        job_type: Key from JOB_TEMPLATES
        quantity: Number of units
        
    Returns:
        List of parts with quantities and prices from price book
    """
    template = JOB_TEMPLATES.get(job_type)
    if not template:
        return []
    
    parts = []
    
    if 'parts_per_unit_config' in template:
        for p in template['parts_per_unit_config']:
            cost = get_part_cost(p['item'])
            price = get_part_price(p['item'])
            parts.append({
                'item': p['item'],
                'qty': p['qty'] * quantity,
                'unit_cost': cost,
                'cost_with_markup': price,
                'line_total': p['qty'] * quantity * price
            })
    elif 'parts_config' in template:
        for p in template['parts_config']:
            cost = get_part_cost(p['item'])
            price = get_part_price(p['item'])
            parts.append({
                'item': p['item'],
                'qty': p['qty'],
                'unit_cost': cost,
                'cost_with_markup': price,
                'line_total': p['qty'] * price
            })
    
    return parts



def generate_invoice(
    estimate: Dict,
    customer_name: str,
    customer_address: str,
    invoice_number: Optional[str] = None
) -> Dict:
    """
    Generate an invoice from an estimate.
    
    Args:
        estimate: Estimate dictionary from generate_estimate()
        customer_name: Client name
        customer_address: Client address
        invoice_number: Optional invoice number (auto-generated if not provided)
        
    Returns:
        Invoice dictionary
    """
    if not invoice_number:
        invoice_number = f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    return {
        "invoice_number": invoice_number,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "due_date": "",  # To be set based on terms
        "customer": {
            "name": customer_name,
            "address": customer_address
        },
        "job": estimate.get('job_name', 'Electrical Work'),
        "line_items": [
            {
                "description": f"Labor: {estimate['labor']['men']} workers × {estimate['labor']['hours']} hrs @ ${estimate['labor']['rate']}/hr",
                "amount": estimate['labor']['total']
            },
            {
                "description": f"Parts & Materials (incl. {int(estimate['parts']['markup_percent'])}% markup)",
                "amount": estimate['parts']['total']
            }
        ],
        "subtotal": estimate['grand_total'],
        "tax": 0.00,  # Add tax calculation if needed
        "total": estimate['grand_total'],
        "notes": estimate.get('notes', ''),
        "status": "draft"
    }


def format_estimate_text(estimate: Dict) -> str:
    """
    Format an estimate as readable text.
    
    Args:
        estimate: Estimate dictionary
        
    Returns:
        Formatted text string
    """
    lines = [
        f"=======================================",
        f"ESTIMATE: {estimate.get('job_name', 'Electrical Work')}",
        f"Date: {estimate.get('created_at', '')[:10]}",
        f"=======================================",
        f"",
        f"LABOR",
        f"  Workers: {estimate['labor']['men']}",
        f"  Hours: {estimate['labor']['hours']}",
        f"  Rate: ${estimate['labor']['rate']:.2f}/hr",
        f"  Subtotal: ${estimate['labor']['total']:.2f}",
        f"",
        f"PARTS & MATERIALS",
    ]
    
    for part in estimate['parts']['items']:
        line_total = part['qty'] * part['cost']
        lines.append(f"  {part['item']}: {part['qty']} x ${part['cost']:.2f} = ${line_total:.2f}")
    
    lines.extend([
        f"  ------------------------------",
        f"  Parts Subtotal: ${estimate['parts']['subtotal']:.2f}",
        f"  Markup ({int(estimate['parts']['markup_percent'])}%): ${estimate['parts']['markup_amount']:.2f}",
        f"  Parts Total: ${estimate['parts']['total']:.2f}",
        f"",
        f"=======================================",
        f"GRAND TOTAL: ${estimate['grand_total']:.2f}",
        f"=======================================",
    ])
    
    if estimate.get('notes'):
        lines.extend([f"", f"Notes: {estimate['notes']}"])
    
    return "\n".join(lines)


# =============================================================================
# CLI INTERFACE (for testing)
# =============================================================================

if __name__ == "__main__":
    print("Beh Brothers Electric - Estimating Engine")
    print("-" * 40)
    
    # Example: 200A Overhead Service
    estimate = generate_estimate("200a_overhead_service")
    print(format_estimate_text(estimate))
    
    print("\n")
    
    # Example: 6 Recessed Lights
    estimate2 = generate_estimate("recessed_lighting", quantity=6)
    print(format_estimate_text(estimate2))
