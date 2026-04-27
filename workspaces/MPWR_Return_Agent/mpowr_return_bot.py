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
            
            # Wait for the status badge to appear
            # MPOWR usually has a badge with classes like "badge", "status-badge", etc.
            # It usually says "Scheduled", "Checked Out", "Completed", etc.
            # We look for the h1 header area which contains the status badge
            self.page.wait_for_selector(".reservation-header-status, .badge", timeout=15000)
            
            # Read all badges and find the one that represents the status
            # It's usually the prominent one near the top. Let's just grab the text of the page header area.
            # Or we can look specifically for a status badge text.
            header_text = self.page.locator("h1, .reservation-header").inner_text().lower()
            
            if "completed" in header_text:
                return "Completed"
            if "returned" in header_text:
                return "Returned"
            if "cancelled" in header_text:
                return "Cancelled"
            if "checked out" in header_text:
                return "Checked Out"
                
            # If not in header text, look for any badge containing standard statuses
            badges = self.page.locator(".badge").all_inner_texts()
            for b in badges:
                bt = b.lower()
                if "completed" in bt: return "Completed"
                if "returned" in bt: return "Returned"
                if "checked out" in bt: return "Checked Out"
                if "scheduled" in bt: return "Scheduled"
                
            return "Unknown"
            
        except Exception as e:
            print(f"[ReturnBot] Failed to get status for {mpwr_id}: {e}")
            return "Error"

    def close(self):
        self.browser.close()
