"""
ohv_storage.py — OHV Permit File Storage

Handles local storage of OHV permit uploads from the customer portal.
Files are saved as {TW_CONFIRMATION}_ohv.{ext} in the ohv_uploads/ directory.

Accepts: JPG, PNG, PDF
Max size: 10MB
"""

import os
from pathlib import Path

UPLOAD_DIR = Path(__file__).parent / "ohv_uploads"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def _ensure_upload_dir():
    """Create the upload directory if it doesn't exist."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _get_extension(filename: str) -> str:
    """Extract and validate file extension."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File type '{ext}' not allowed. Accepted: {', '.join(ALLOWED_EXTENSIONS)}")
    return ext


def save_ohv_permit(tw_confirmation: str, file_bytes: bytes, filename: str) -> str:
    """
    Save an OHV permit file to local storage.

    Args:
        tw_confirmation: TripWorks confirmation code (used as filename prefix)
        file_bytes: Raw file content
        filename: Original filename (for extension detection)

    Returns:
        Absolute path to the saved file

    Raises:
        ValueError: If file type is not allowed or file is too large
    """
    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError(f"File too large ({len(file_bytes) / 1024 / 1024:.1f}MB). Max: 10MB")

    ext = _get_extension(filename)
    _ensure_upload_dir()

    # Sanitize confirmation code for filesystem safety
    safe_conf = tw_confirmation.replace("/", "_").replace("\\", "_").strip().upper()
    save_filename = f"{safe_conf}_ohv{ext}"
    save_path = UPLOAD_DIR / save_filename

    with open(save_path, "wb") as f:
        f.write(file_bytes)

    print(f"[OHV] Saved permit for {tw_confirmation}: {save_path}")
    return str(save_path.absolute())


def get_ohv_path(tw_confirmation: str) -> str | None:
    """
    Check if an OHV permit exists for the given confirmation code.

    Returns:
        Absolute path if file exists, None otherwise
    """
    safe_conf = tw_confirmation.replace("/", "_").replace("\\", "_").strip().upper()

    for ext in ALLOWED_EXTENSIONS:
        path = UPLOAD_DIR / f"{safe_conf}_ohv{ext}"
        if path.exists():
            return str(path.absolute())

    return None


def ohv_exists(tw_confirmation: str) -> bool:
    """Check if an OHV permit has been uploaded for this reservation."""
    return get_ohv_path(tw_confirmation) is not None
