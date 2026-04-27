"""
api_models.py — Pydantic Models for Epic 4x4 Dashboard API

Defines typed request/response models for:
  - Staff Arrival Board
  - TV Dashboard
  - Customer Portal
  - Webhook events
"""

from pydantic import BaseModel
from typing import Optional


# =============================================================================
# Shared Sub-Models
# =============================================================================

class WaiverProgress(BaseModel):
    """Tracks waiver completion as a fraction with signer names."""
    completed: int = 0          # e.g., 1
    expected: int = 0           # e.g., 2
    names: list[str] = []       # ["Bobby G.", "Sarah G."]

    @property
    def is_complete(self) -> bool:
        return self.expected > 0 and self.completed >= self.expected


# =============================================================================
# Staff Dashboard / TV Board Models
# =============================================================================

class ArrivalGuest(BaseModel):
    """A single guest/reservation row on the arrival board."""
    tw_confirmation: str
    tw_order_id: str = ""
    guest_name: str
    booking_type: str                   # "Tour" or "Rental"
    activity_name: str
    vehicle_model: str = ""
    vehicle_qty: int = 1
    party_size: int = 1
    activity_time: str = ""
    activity_date: str = ""
    overall_status: str = "not_ready"   # "ready" or "not_ready"

    # Waiver statuses
    epic_waivers: WaiverProgress = WaiverProgress()
    polaris_waivers: WaiverProgress = WaiverProgress()

    # OHV (rentals only) — V2: multi-driver tracking
    ohv_required: bool = False
    ohv_uploaded: bool = False
    ohv_expected: int = 0
    ohv_complete: int = 0
    ohv_permit_names: list[str] = []

    # Deposits / Payment
    deposit_status: str = "due"         # "due", "collected", "compensated"
    amount_due: float = 0.0
    amount_paid: float = 0.0
    adventure_assure: str = "None"      # "None", "Free", "Premium"

    # Check-in
    checked_in: bool = False
    checked_in_at: Optional[str] = None

    # V2: Rental return tracking
    rental_return_time: str = ""
    rental_status: str = ""             # "", "On Ride", "Returned", "Overdue"

    # V2: Primary rider (booking holder)
    primary_rider: str = ""

    # Links
    tw_link: str = ""
    mpwr_link: str = ""
    mpwr_number: str = ""
    mpwr_waiver_link: str = ""          # Polaris waiver URL for customer portal
    mpwr_waiver_qr_url: str = ""        # Supabase Storage URL to QR code PNG
    customer_portal_link: str = ""

    # V2: Signed waiver PDFs
    epic_waiver_pdfs: list[str] = []
    polaris_waiver_pdfs: list[str] = []

    # Notes
    notes: str = ""
    trip_method: str = ""
    trip_safe: str = ""                 # "Purchased", "Declined", or ""

    # TripWorks booking status (from status webhook)
    tw_status: str = ""                 # "Not Checked In", "Checked In", "Rental Out", etc.


class ArrivalBoardResponse(BaseModel):
    """Response for GET /api/arrivals — staff dashboard data."""
    now_next: list[ArrivalGuest] = []       # 0-30 min window
    upcoming: list[ArrivalGuest] = []       # 30-90 min window
    checked_in: list[ArrivalGuest] = []     # Already checked in today
    last_refresh: str = ""
    active_count: int = 0
    total_today: int = 0


class TVBoardResponse(BaseModel):
    """Response for GET /api/tv/rentals or /api/tv/tours."""
    now_next: list[ArrivalGuest] = []
    upcoming: list[ArrivalGuest] = []
    last_refresh: str = ""
    filter_type: str = "all"               # "rental", "tour", "all"


# =============================================================================
# Customer Portal Models
# =============================================================================

class CustomerPortalResponse(BaseModel):
    """Response for GET /api/portal/{tw_conf}."""
    guest_name: str
    activity_name: str
    booking_type: str
    activity_date: str
    activity_time: str
    countdown_target_iso: str = ""          # ISO timestamp for JS countdown

    epic_waivers: WaiverProgress = WaiverProgress()
    polaris_waivers: WaiverProgress = WaiverProgress()
    epic_waiver_url: str = ""               # TripWorks waiver portal
    polaris_waiver_url: str = ""            # MPWR waiver link from sheet
    polaris_waiver_qr_url: str = ""         # Supabase Storage URL to QR code PNG

    ohv_required: bool = False
    ohv_uploaded: bool = False

    vehicle_model: str = ""
    party_size: int = 1
    rental_return_time: str = ""


class OHVUploadResponse(BaseModel):
    """Response for POST /api/portal/{tw_conf}/ohv."""
    success: bool
    message: str
    file_path: Optional[str] = None


# =============================================================================
# Action Models
# =============================================================================

class CheckInRequest(BaseModel):
    staff_name: str = "Staff"


class CollectPaymentRequest(BaseModel):
    staff_name: str = "Staff"
    notes: str = ""


class UpdateNotesRequest(BaseModel):
    notes: str


# =============================================================================
# Webhook Models
# =============================================================================

class WaiverCompletedWebhook(BaseModel):
    """Expected shape of a TripWorks guest waiver completion webhook.
    Actual field names TBD — will update after receiving sample payload."""
    confirmation_code: Optional[str] = None
    guest_name: Optional[str] = None
    waiver_type: Optional[str] = None
    # Raw payload stored for inspection
    raw: Optional[dict] = None
