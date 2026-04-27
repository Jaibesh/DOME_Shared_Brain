"""
main.py — Epic 4x4 MPOWR Reconciliation Daemon

Production hardening applied April 24, 2026:
  - Deprecated legacy Google Sheets integration (moved to Supabase)
  - Deprecated mock TripWorks API (moved to webhook-first architecture)
  - Deprecated in-memory dashboard cache (handled by Waiver_Dashboard)
  - Transformed into a lightweight background task scheduler for MPOWR scraping
  - Removed dead frontend mount (this daemon has no UI)
  - Migrated from deprecated @app.on_event to lifespan context manager
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, Header, HTTPException
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz

from scraper import run_mpowr_scraper

# Simple API key auth
CREATOR_API_KEY = os.getenv("CREATOR_API_KEY", "")

def _verify_api_key(x_api_key: str = Header(default="")):
    """Verify API key for protected endpoints."""
    if CREATOR_API_KEY and x_api_key != CREATOR_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")


scheduler = BackgroundScheduler()


def scheduled_job():
    # Only run between 6 AM and 10 PM
    now = datetime.now(pytz.timezone('America/Denver'))
    if now.hour < 6 or now.hour >= 22:
        print(f"[{now}] Outside operating hours. Skipping MPOWR sync run.")
        return
        
    print(f"[{now}] Starting hourly MPOWR waiver sync run...")
    
    email = os.getenv("MPOWR_EMAIL")
    pwd = os.getenv("MPOWR_PASSWORD")
    
    if not email or not pwd:
        print("Missing MPOWR_EMAIL or MPOWR_PASSWORD in .env")
        return
        
    try:
        run_mpowr_scraper(email, pwd)
    except Exception as e:
        print(f"[{now}] Scraping failed abruptly: {e}")


def _cleanup_screenshots(max_age_days: int = 7):
    """Remove old screenshot files to prevent unbounded disk growth."""
    screenshots_dir = os.path.join(os.path.dirname(__file__), "screenshots")
    if not os.path.exists(screenshots_dir):
        return
    cutoff = datetime.now().timestamp() - (max_age_days * 86400)
    removed = 0
    for fname in os.listdir(screenshots_dir):
        fpath = os.path.join(screenshots_dir, fname)
        if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
            try:
                os.remove(fpath)
                removed += 1
            except OSError:
                pass
    if removed:
        print(f"[Startup] Cleaned up {removed} old screenshot(s).")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    # MPOWR waiver reconciliation on the hour
    scheduler.add_job(scheduled_job, 'cron', minute=0)
    
    # Trigger an immediate run so it doesn't block the boot sequence
    run_time = datetime.now(pytz.timezone('America/Denver'))
    scheduler.add_job(scheduled_job, 'date', run_date=run_time)
    
    # Clean up old screenshots
    _cleanup_screenshots()
    
    scheduler.start()
    print("Scheduler started: MPOWR Reconciliation (hourly + immediate startup run)")
    
    yield
    
    scheduler.shutdown()
    print("Scheduler stopped.")


app = FastAPI(title="Epic 4x4 Waiver Reconciliation Daemon", lifespan=lifespan)


@app.get("/api/health")
def health():
    """Health check endpoint for monitoring. Returns system status."""
    return {
        "status": "ok",
        "mode": "standalone_scheduler",
        "server_time": datetime.now(pytz.timezone('America/Denver')).isoformat(),
    }

@app.post("/api/trigger_sync")
def trigger_sync(background_tasks: BackgroundTasks, x_api_key: str = Header(default="")):
    """Allows manual trigger of a sync"""
    _verify_api_key(x_api_key)
    background_tasks.add_task(scheduled_job)
    return {"status": "Sync triggered in background"}

if __name__ == "__main__":
    import uvicorn
    # Run the FastAPI server to keep the lifespan scheduler alive
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=False)
