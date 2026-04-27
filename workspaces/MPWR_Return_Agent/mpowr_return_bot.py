import os
import sys

# Add shared modules
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "shared"))
from mpowr_browser import MpowrBrowser


class MpowrReturnBot:
    def __init__(self):
        self.browser = MpowrBrowser("MPWR_Return_Agent")
        self.browser.login()
        self.page = self.browser.page

    def get_reservation_status(self, mpwr_id: str) -> str:
        """Navigates to the reservation and extracts its current status."""
        url = f"https://outfitter.polarisadventures.com/reservations/{mpwr_id}"
        print(f"[ReturnBot] Navigating to {url}")
        
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            # 1. Primary Strategy: Look for standard MPOWR badges
            try:
                self.page.wait_for_selector(".reservation-header-status, .badge", timeout=10000)
                # Check header text first
                header_texts = self.page.locator("h1, .reservation-header").all_inner_texts()
                for ht in header_texts:
                    ht_lower = ht.lower()
                    if "completed" in ht_lower: return "Completed"
                    if "returned" in ht_lower: return "Returned"
                    if "checked out" in ht_lower: return "Checked Out"
                    if "cancelled" in ht_lower: return "Cancelled"
                
                # Check badges
                badges = self.page.locator(".badge").all_inner_texts()
                for b in badges:
                    bt = b.lower()
                    if "completed" in bt: return "Completed"
                    if "returned" in bt: return "Returned"
                    if "checked out" in bt: return "Checked Out"
                    if "scheduled" in bt: return "Scheduled"
            except Exception:
                pass # Timeout on specific selectors, fall back to aggressive text search
                
            # 2. Fallback Strategy: Aggressive DOM-traversal via get_by_text
            # If classes change, we just search the visible page text for the exact status words
            print(f"[ReturnBot] Fallback text search for {mpwr_id}...")
            
            # Wait for the page body to be stable
            self.page.wait_for_selector("body", timeout=5000)
            
            for status in ["Completed", "COMPLETED", "Returned", "RETURNED"]:
                if self.page.get_by_text(status, exact=True).is_visible():
                    return "Completed" if "complete" in status.lower() else "Returned"
                    
            for status in ["Checked Out", "CHECKED OUT"]:
                if self.page.get_by_text(status, exact=True).is_visible():
                    return "Checked Out"
                    
            for status in ["Cancelled", "CANCELLED"]:
                if self.page.get_by_text(status, exact=True).is_visible():
                    return "Cancelled"
                    
            for status in ["Scheduled", "SCHEDULED"]:
                if self.page.get_by_text(status, exact=True).is_visible():
                    return "Scheduled"
                
            return "Unknown"
            
        except Exception as e:
            print(f"[ReturnBot] Failed to get status for {mpwr_id}: {e}")
            return "Error"

    def close(self):
        self.browser.close()
