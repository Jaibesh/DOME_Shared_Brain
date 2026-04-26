"""
HCP Client - Unified interface for Housecall Pro API.

Supports both mock (local server) and live (HCP production) modes.
Configure via environment variables:
  HCP_MODE=mock|live
  HCP_API_KEY=your-api-key
  HCP_BASE_URL=http://localhost:8000 (mock) or https://api.housecallpro.com (live)
"""
import os
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class HCPClient:
    """Housecall Pro API Client."""
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        mode: Optional[str] = None
    ):
        self.mode = mode or os.getenv("HCP_MODE", "mock")
        
        if self.mode == "live":
            self.base_url = base_url or os.getenv("HCP_BASE_URL", "https://api.housecallpro.com")
            self.api_key = api_key or os.getenv("HCP_API_KEY")
            if not self.api_key:
                raise ValueError("HCP_API_KEY required for live mode")
        else:
            self.base_url = base_url or os.getenv("HCP_BASE_URL", "http://localhost:8000")
            self.api_key = api_key or "mock-api-key"
        
        self.session = requests.Session()
        
        # Configure robust retries
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })
        
        logger.info(f"HCPClient initialized in {self.mode} mode → {self.base_url}")
    
    def _request(self, method: str, endpoint: str, data: dict = None, params: dict = None) -> Dict[str, Any]:
        """Make an API request."""
        url = f"{self.base_url}/v1{endpoint}"
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                json=data,
                params=params
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"HCP API error: {e}")
            raise
    
    # ============ Customer Methods ============
    def list_customers(self, page: int = 1, per_page: int = 25) -> Dict[str, Any]:
        """List all customers."""
        return self._request("GET", "/customers", params={"page": page, "per_page": per_page})
    
    def get_customer(self, customer_id: str) -> Dict[str, Any]:
        """Get a customer by ID."""
        return self._request("GET", f"/customers/{customer_id}")
    
    def create_customer(
        self,
        first_name: str,
        last_name: str,
        email: str = None,
        phone: str = None,
        address: dict = None,
        lead_source: str = None
    ) -> Dict[str, Any]:
        """Create a new customer."""
        data = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "address": address,
            "lead_source": lead_source
        }
        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}
        return self._request("POST", "/customers", data=data)
    
    def update_customer(self, customer_id: str, updates: dict) -> Dict[str, Any]:
        """Update a customer."""
        return self._request("PUT", f"/customers/{customer_id}", data=updates)
    
    def delete_customer(self, customer_id: str) -> Dict[str, Any]:
        """Delete a customer."""
        return self._request("DELETE", f"/customers/{customer_id}")
    
    # ============ Job Methods ============
    def list_jobs(
        self,
        customer_id: str = None,
        status: str = None,
        page: int = 1,
        per_page: int = 25
    ) -> Dict[str, Any]:
        """List jobs with optional filters."""
        params = {"page": page, "per_page": per_page}
        if customer_id:
            params["customer_id"] = customer_id
        if status:
            params["status"] = status
        return self._request("GET", "/jobs", params=params)
    
    def get_job(self, job_id: str) -> Dict[str, Any]:
        """Get a job by ID."""
        return self._request("GET", f"/jobs/{job_id}")
    
    def create_job(
        self,
        customer_id: str,
        description: str,
        address: dict = None,
        scheduled_start: datetime = None,
        scheduled_end: datetime = None
    ) -> Dict[str, Any]:
        """Create a new job."""
        data = {
            "customer_id": customer_id,
            "description": description,
            "address": address,
            "scheduled_start": scheduled_start.isoformat() if scheduled_start else None,
            "scheduled_end": scheduled_end.isoformat() if scheduled_end else None
        }
        data = {k: v for k, v in data.items() if v is not None}
        return self._request("POST", "/jobs", data=data)
    
    def schedule_job(self, job_id: str, start: datetime, end: datetime) -> Dict[str, Any]:
        """Schedule a job."""
        return self._request("POST", f"/jobs/{job_id}/schedule", params={
            "scheduled_start": start.isoformat(),
            "scheduled_end": end.isoformat()
        })
    
    def start_job(self, job_id: str) -> Dict[str, Any]:
        """Mark a job as in progress."""
        return self._request("POST", f"/jobs/{job_id}/start")
    
    def complete_job(self, job_id: str) -> Dict[str, Any]:
        """Mark a job as completed."""
        return self._request("POST", f"/jobs/{job_id}/complete")
    
    # ============ Estimate Methods ============
    def list_estimates(
        self,
        customer_id: str = None,
        status: str = None,
        page: int = 1,
        per_page: int = 25
    ) -> Dict[str, Any]:
        """List estimates with optional filters."""
        params = {"page": page, "per_page": per_page}
        if customer_id:
            params["customer_id"] = customer_id
        if status:
            params["status"] = status
        return self._request("GET", "/estimates", params=params)
    
    def get_estimate(self, estimate_id: str) -> Dict[str, Any]:
        """Get an estimate by ID."""
        return self._request("GET", f"/estimates/{estimate_id}")
    
    def create_estimate(
        self,
        customer_id: str,
        line_items: List[dict],
        notes: str = None,
        valid_until: datetime = None
    ) -> Dict[str, Any]:
        """Create a new estimate."""
        data = {
            "customer_id": customer_id,
            "line_items": line_items,
            "notes": notes,
            "valid_until": valid_until.isoformat() if valid_until else None
        }
        data = {k: v for k, v in data.items() if v is not None}
        return self._request("POST", "/estimates", data=data)
    
    def send_estimate(self, estimate_id: str) -> Dict[str, Any]:
        """Send an estimate to the customer."""
        return self._request("POST", f"/estimates/{estimate_id}/send")
    
    def approve_estimate(self, estimate_id: str) -> Dict[str, Any]:
        """Approve an estimate (for testing)."""
        return self._request("POST", f"/estimates/{estimate_id}/approve")
    
    def convert_estimate_to_job(self, estimate_id: str) -> Dict[str, Any]:
        """Convert an approved estimate to a job."""
        return self._request("POST", f"/estimates/{estimate_id}/convert-to-job")
    
    # ============ Invoice Methods ============
    def list_invoices(
        self,
        customer_id: str = None,
        status: str = None,
        page: int = 1,
        per_page: int = 25
    ) -> Dict[str, Any]:
        """List invoices with optional filters."""
        params = {"page": page, "per_page": per_page}
        if customer_id:
            params["customer_id"] = customer_id
        if status:
            params["status"] = status
        return self._request("GET", "/invoices", params=params)
    
    def get_invoice(self, invoice_id: str) -> Dict[str, Any]:
        """Get an invoice by ID."""
        return self._request("GET", f"/invoices/{invoice_id}")
    
    def create_invoice(
        self,
        customer_id: str,
        line_items: List[dict],
        job_id: str = None,
        notes: str = None,
        due_date: datetime = None
    ) -> Dict[str, Any]:
        """Create a new invoice."""
        data = {
            "customer_id": customer_id,
            "job_id": job_id,
            "line_items": line_items,
            "notes": notes,
            "due_date": due_date.isoformat() if due_date else None
        }
        data = {k: v for k, v in data.items() if v is not None}
        return self._request("POST", "/invoices", data=data)
    
    def send_invoice(self, invoice_id: str) -> Dict[str, Any]:
        """Send an invoice to the customer."""
        return self._request("POST", f"/invoices/{invoice_id}/send")
    
    def record_payment(self, invoice_id: str, amount: float) -> Dict[str, Any]:
        """Record a payment on an invoice."""
        return self._request("POST", f"/invoices/{invoice_id}/record-payment", params={"amount": amount})
    
    # ============ Utility Methods ============
    def health_check(self) -> Dict[str, Any]:
        """Check API health (mock only)."""
        return self._request("GET", "/../health")
    
    def get_webhook_log(self) -> Dict[str, Any]:
        """Get webhook event log (mock only)."""
        return self._request("GET", "/webhooks/log")
    
    def reset_mock_data(self) -> Dict[str, Any]:
        """Reset all mock data (mock only)."""
        if self.mode != "mock":
            raise ValueError("reset_mock_data only available in mock mode")
        return self._request("DELETE", "/data/reset")
