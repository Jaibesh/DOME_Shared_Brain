"""
DOME Framework - Job Tracker
Tracks jobs from quote to completion for Beh Brothers Electric.
"""

import os
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv
from utils import load_json, save_json, get_next_customer_id

# Load environment
load_dotenv()

# Configuration
JOBS_FILE = "brain/sources/jobs.json"
CUSTOMERS_FILE = "brain/sources/customers.json"

# Job Status Pipeline
JOB_STATUSES = [
    "quote_requested",    # Initial inquiry
    "quote_sent",         # Estimate provided
    "approved",           # Customer accepted quote
    "scheduled",          # Job date set
    "in_progress",        # Work underway
    "completed",          # Work finished
    "invoiced",           # Invoice sent
    "paid",               # Payment received
    "cancelled"           # Job cancelled
]


# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def get_next_job_id(jobs_file: str = JOBS_FILE) -> str:
    """
    Generate the next job ID in sequence.
    
    Returns:
        Next available ID (e.g., "JOB-0005")
    """
    jobs = load_json(jobs_file, [])
    
    if not jobs:
        return "JOB-0001"
    
    max_num = 0
    for job in jobs:
        id_str = job.get('id', 'JOB-0000')
        try:
            num = int(id_str.split('-')[1])
            max_num = max(max_num, num)
        except (IndexError, ValueError):
            continue
    
    return f"JOB-{max_num + 1:04d}"


def create_job(
    customer_id: str,
    job_type: str,
    description: str,
    address: Optional[str] = None,
    estimate_total: float = 0.0,
    notes: str = ""
) -> Dict:
    """
    Create a new job record.
    
    Args:
        customer_id: Customer ID (e.g., "BEH-0001")
        job_type: Type of job (e.g., "200a_overhead_service")
        description: Human-readable description
        address: Job site address (defaults to customer address)
        estimate_total: Estimated total cost
        notes: Additional notes
        
    Returns:
        Created job dictionary
    """
    job_id = get_next_job_id()
    now = datetime.now()
    
    # Get customer address if not provided
    if not address:
        customers = load_json(CUSTOMERS_FILE, [])
        for customer in customers:
            if customer.get('id') == customer_id:
                address = customer.get('address', '')
                break
    
    job = {
        "id": job_id,
        "customer_id": customer_id,
        "job_type": job_type,
        "description": description,
        "address": address or "",
        "status": "quote_requested",
        "estimate_total": estimate_total,
        "invoice_total": 0.0,
        "invoice_number": "",
        "scheduled_date": "",
        "scheduled_time": "",
        "completed_date": "",
        "paid_date": "",
        "men_assigned": 0,
        "hours_estimated": 0.0,
        "hours_actual": 0.0,
        "parts_list": [],
        "notes": notes,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "history": [
            {"status": "quote_requested", "timestamp": now.isoformat(), "note": "Job created"}
        ]
    }
    
    # Save to jobs file
    jobs = load_json(JOBS_FILE, [])
    jobs.append(job)
    save_json(JOBS_FILE, jobs)
    
    # Link to customer
    _link_job_to_customer(job_id, customer_id)
    
    return job


def update_job_status(
    job_id: str,
    new_status: str,
    note: str = ""
) -> Dict:
    """
    Update a job's status with history tracking.
    
    Args:
        job_id: Job ID to update
        new_status: New status (must be in JOB_STATUSES)
        note: Optional note about the status change
        
    Returns:
        Updated job dictionary or error dict
    """
    if new_status not in JOB_STATUSES:
        return {"error": f"Invalid status. Must be one of: {JOB_STATUSES}"}
    
    jobs = load_json(JOBS_FILE, [])
    
    for job in jobs:
        if job.get('id') == job_id:
            old_status = job.get('status')
            now = datetime.now()
            
            job['status'] = new_status
            job['updated_at'] = now.isoformat()
            
            # Add to history
            history_entry = {
                "status": new_status,
                "timestamp": now.isoformat(),
                "note": note or f"Status changed from {old_status} to {new_status}"
            }
            if 'history' not in job:
                job['history'] = []
            job['history'].append(history_entry)
            
            # Special status handling
            if new_status == "completed" and not job.get('completed_date'):
                job['completed_date'] = now.strftime('%Y-%m-%d')
            elif new_status == "paid" and not job.get('paid_date'):
                job['paid_date'] = now.strftime('%Y-%m-%d')
            
            save_json(JOBS_FILE, jobs)
            return job
    
    return {"error": f"Job {job_id} not found"}


def schedule_job(
    job_id: str,
    date: str,
    time: str,
    men: int = 2,
    hours: float = 0.0
) -> Dict:
    """
    Schedule a job for a specific date/time.
    
    Args:
        job_id: Job ID to schedule
        date: Date string (YYYY-MM-DD)
        time: Time string (e.g., "9:00 AM")
        men: Number of workers assigned
        hours: Estimated hours
        
    Returns:
        Updated job dictionary
    """
    jobs = load_json(JOBS_FILE, [])
    
    for job in jobs:
        if job.get('id') == job_id:
            now = datetime.now()
            
            job['scheduled_date'] = date
            job['scheduled_time'] = time
            job['men_assigned'] = men
            if hours > 0:
                job['hours_estimated'] = hours
            job['updated_at'] = now.isoformat()
            
            # Update status if still in early stages
            if job.get('status') in ['quote_requested', 'quote_sent', 'approved']:
                job['status'] = 'scheduled'
                job['history'].append({
                    "status": "scheduled",
                    "timestamp": now.isoformat(),
                    "note": f"Scheduled for {date} @ {time}"
                })
            
            save_json(JOBS_FILE, jobs)
            return job
    
    return {"error": f"Job {job_id} not found"}


def add_invoice_to_job(
    job_id: str,
    invoice_number: str,
    total: float
) -> Dict:
    """
    Add invoice details to a job.
    
    Args:
        job_id: Job ID
        invoice_number: Invoice number
        total: Invoice total
        
    Returns:
        Updated job dictionary
    """
    jobs = load_json(JOBS_FILE, [])
    
    for job in jobs:
        if job.get('id') == job_id:
            now = datetime.now()
            
            job['invoice_number'] = invoice_number
            job['invoice_total'] = total
            job['updated_at'] = now.isoformat()
            
            # Update status
            if job.get('status') not in ['paid', 'invoiced']:
                job['status'] = 'invoiced'
                job['history'].append({
                    "status": "invoiced",
                    "timestamp": now.isoformat(),
                    "note": f"Invoice {invoice_number} sent for ${total:.2f}"
                })
            
            save_json(JOBS_FILE, jobs)
            return job
    
    return {"error": f"Job {job_id} not found"}


def get_job(job_id: str) -> Optional[Dict]:
    """Get a single job by ID."""
    jobs = load_json(JOBS_FILE, [])
    for job in jobs:
        if job.get('id') == job_id:
            return job
    return None


def get_jobs_by_status(status: str) -> List[Dict]:
    """Get all jobs with a specific status."""
    jobs = load_json(JOBS_FILE, [])
    return [j for j in jobs if j.get('status') == status]


def get_jobs_by_customer(customer_id: str) -> List[Dict]:
    """Get all jobs for a specific customer."""
    jobs = load_json(JOBS_FILE, [])
    return [j for j in jobs if j.get('customer_id') == customer_id]


def get_upcoming_jobs(days: int = 7) -> List[Dict]:
    """Get jobs scheduled within the next N days."""
    jobs = load_json(JOBS_FILE, [])
    today = datetime.now().date()
    future = today + timedelta(days=days)
    
    upcoming = []
    for job in jobs:
        if job.get('scheduled_date'):
            try:
                job_date = datetime.strptime(job['scheduled_date'], '%Y-%m-%d').date()
                if today <= job_date <= future:
                    upcoming.append(job)
            except ValueError:
                continue
    
    return sorted(upcoming, key=lambda x: x.get('scheduled_date', ''))


def get_pending_invoices() -> List[Dict]:
    """Get all jobs that are invoiced but not paid."""
    return get_jobs_by_status('invoiced')


def get_all_jobs() -> List[Dict]:
    """Get all jobs."""
    return load_json(JOBS_FILE, [])


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _link_job_to_customer(job_id: str, customer_id: str) -> None:
    """Add job ID to customer's jobs array."""
    customers = load_json(CUSTOMERS_FILE, [])
    
    for customer in customers:
        if customer.get('id') == customer_id:
            if 'jobs' not in customer:
                customer['jobs'] = []
            if job_id not in customer['jobs']:
                customer['jobs'].append(job_id)
            break
    
    save_json(CUSTOMERS_FILE, customers)


def format_job_summary(job: Dict) -> str:
    """Format a job as a readable summary string."""
    lines = [
        f"Job: {job.get('id')} - {job.get('description')}",
        f"Status: {job.get('status', 'unknown').replace('_', ' ').title()}",
        f"Customer: {job.get('customer_id')}",
        f"Address: {job.get('address')}",
    ]
    
    if job.get('scheduled_date'):
        lines.append(f"Scheduled: {job.get('scheduled_date')} @ {job.get('scheduled_time')}")
    
    if job.get('estimate_total'):
        lines.append(f"Estimate: ${job.get('estimate_total'):.2f}")
    
    if job.get('invoice_total'):
        lines.append(f"Invoice: ${job.get('invoice_total'):.2f} ({job.get('invoice_number')})")
    
    return "\n".join(lines)


# =============================================================================
# CLI INTERFACE (for testing)
# =============================================================================

if __name__ == "__main__":
    print("Beh Brothers Electric - Job Tracker")
    print("-" * 40)
    
    # Example: Create a test job
    job = create_job(
        customer_id="BEH-0001",
        job_type="200a_overhead_service",
        description="200A Overhead Service Upgrade",
        estimate_total=2500.00,
        notes="Power company scheduled for 2/15"
    )
    
    print(f"Created job: {job['id']}")
    print(format_job_summary(job))
    
    print("\n")
    
    # Schedule it
    job = schedule_job(job['id'], "2026-02-15", "9:00 AM", men=2, hours=8)
    print(f"Scheduled job: {job['id']}")
    print(format_job_summary(job))
