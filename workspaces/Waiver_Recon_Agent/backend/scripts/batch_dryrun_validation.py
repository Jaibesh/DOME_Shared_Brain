# -*- coding: utf-8 -*-
"""
Dry-run validation: 2 batches of 20 from the BOTTOM of the Google Sheet.

This script:
1. Fetches all pending rows from the sheet
2. Takes the LAST 40 (bottom of sheet = most recent bookings)
3. Validates data mapping for all 40
4. Runs 2 batches of 20 against live MPOWR in DRY_RUN mode
5. Does NOT write results back to the sheet

Expected time: ~15-20 minutes per batch (20 × 45-60s each)
"""
import sys
import os

# Ensure backend modules are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', '.env'))

from sheets import get_sheets_client, _parse_activity_date
from data_mapper import build_customer_payload_from_row
from mpowr_creator_bot import MpowrCreatorBot
from slack_notifier import SlackNotifier
from datetime import date
import time

BATCH_SIZE = 20
NUM_BATCHES = 2
TOTAL_ROWS = BATCH_SIZE * NUM_BATCHES  # 40

slack = SlackNotifier()


def main():
    print("=" * 70)
    print("DRY-RUN VALIDATION: 2 batches of 20 from bottom of sheet")
    print("=" * 70)

    # ── Phase 1: Fetch all pending rows ──────────────────────────────────
    print("\n[Phase 1] Fetching pending rows from Google Sheet...")
    client = get_sheets_client()
    if not client:
        print("ERROR: Cannot connect to Google Sheets")
        return

    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    sheet = client.open_by_key(sheet_id).sheet1
    records = sheet.get_all_records(value_render_option="FORMATTED_VALUE")
    print(f"  Total rows in sheet: {len(records)}")

    # Filter to pending only (same logic as scan_for_pending_creations)
    today = date.today()
    pending = []
    skipped_past = 0
    skipped_filled = 0

    for idx, row in enumerate(records):
        row_index = idx + 2
        first_name = str(row.get("First Name", "")).strip()
        last_name = str(row.get("Last Name", "")).strip()
        activity_date = str(row.get("Activity Date", "")).strip()
        mpwr_conf = str(row.get("MPWR Confirmation Number", "")).strip()

        if not first_name or not last_name:
            continue
        if not activity_date:
            continue

        # Filter past dates
        parsed = _parse_activity_date(activity_date)
        if parsed and parsed < today:
            skipped_past += 1
            continue

        # Skip already-filled rows
        if mpwr_conf and not mpwr_conf.upper().startswith("RETRY_"):
            skipped_filled += 1
            continue

        row["_row_index"] = row_index
        pending.append(row)

    print(f"  Pending (future, unfilled): {len(pending)}")
    print(f"  Skipped (past dates): {skipped_past}")
    print(f"  Skipped (already filled): {skipped_filled}")

    if len(pending) < TOTAL_ROWS:
        print(f"  ⚠️ Only {len(pending)} pending rows, adjusting to that")
        rows_to_process = pending  # Take all if fewer than 40
    else:
        # Take the LAST 40 (bottom of sheet)
        rows_to_process = pending[-TOTAL_ROWS:]
        print(f"  Taking last {TOTAL_ROWS} rows (rows {rows_to_process[0]['_row_index']}-{rows_to_process[-1]['_row_index']})")

    # ── Phase 2: Build payloads and validate ─────────────────────────────
    print(f"\n[Phase 2] Building and validating {len(rows_to_process)} payloads...")
    payloads = []
    errors = []

    for row in rows_to_process:
        row_idx = row["_row_index"]
        payload = build_customer_payload_from_row(row, row_idx)

        if payload.get("error"):
            errors.append((row_idx, payload["error"]))
            print(f"  ❌ Row {row_idx}: {payload['error']}")
        else:
            payloads.append(payload)
            name = f"{payload['first_name']} {payload['last_name']}"
            print(f"  ✅ Row {row_idx}: {name} | {payload['mpowr_activity']} | "
                  f"{payload['mpowr_vehicle']} x{payload['vehicle_qty']} | "
                  f"{payload['activity_date']} {payload['activity_time']} | "
                  f"${payload['target_price']}")

    print(f"\n  Validated: {len(payloads)} OK, {len(errors)} errors")

    if not payloads:
        print("ERROR: No valid payloads to process!")
        return

    # ── Phase 3: Split into batches ──────────────────────────────────────
    batch_1 = payloads[:BATCH_SIZE]
    batch_2 = payloads[BATCH_SIZE:BATCH_SIZE * 2] if len(payloads) > BATCH_SIZE else []

    print(f"\n  Batch 1: {len(batch_1)} reservations")
    print(f"  Batch 2: {len(batch_2)} reservations")

    # ── Phase 4: Run Batch 1 ─────────────────────────────────────────────
    email = os.getenv("MPOWR_EMAIL")
    pwd = os.getenv("MPOWR_PASSWORD")

    print(f"\n{'=' * 70}")
    print(f"[Phase 4] BATCH 1: Processing {len(batch_1)} reservations (DRY RUN)")
    print(f"{'=' * 70}")

    batch1_start = time.time()
    bot1 = MpowrCreatorBot(email=email, password=pwd, headless=True, dry_run=True)
    results1 = bot1.create_batch(batch_1)
    batch1_time = time.time() - batch1_start

    # Summarize Batch 1
    print(f"\n{'─' * 40}")
    print(f"BATCH 1 SUMMARY ({batch1_time:.0f}s)")
    print(f"{'─' * 40}")
    for payload, result in zip(batch_1, results1):
        name = f"{payload['first_name']} {payload['last_name']}"
        status_icon = {"dry_run": "✅", "error": "❌", "duplicate": "⚠️"}.get(result.status, "❓")
        print(f"  {status_icon} Row {payload['sheet_row_index']}: {result.status} | {name} | {payload['mpowr_activity']}")
        if result.error_message and result.status == "error":
            print(f"      Error: {result.error_message}")

    b1_ok = sum(1 for r in results1 if r.status == "dry_run")
    b1_err = sum(1 for r in results1 if r.status == "error")
    b1_dup = sum(1 for r in results1 if r.status == "duplicate")
    print(f"\n  Results: {b1_ok} dry_run, {b1_err} errors, {b1_dup} duplicates")

    # Send Slack summary for batch 1
    slack.send_success_summary(
        created_count=0,
        failed_count=b1_err,
        skipped_count=b1_ok,
        duplicates_count=b1_dup
    )

    # ── Phase 5: Run Batch 2 ─────────────────────────────────────────────
    if batch_2:
        print(f"\n{'=' * 70}")
        print(f"[Phase 5] BATCH 2: Processing {len(batch_2)} reservations (DRY RUN)")
        print(f"{'=' * 70}")

        batch2_start = time.time()
        bot2 = MpowrCreatorBot(email=email, password=pwd, headless=True, dry_run=True)
        results2 = bot2.create_batch(batch_2)
        batch2_time = time.time() - batch2_start

        print(f"\n{'─' * 40}")
        print(f"BATCH 2 SUMMARY ({batch2_time:.0f}s)")
        print(f"{'─' * 40}")
        for payload, result in zip(batch_2, results2):
            name = f"{payload['first_name']} {payload['last_name']}"
            status_icon = {"dry_run": "✅", "error": "❌", "duplicate": "⚠️"}.get(result.status, "❓")
            print(f"  {status_icon} Row {payload['sheet_row_index']}: {result.status} | {name} | {payload['mpowr_activity']}")
            if result.error_message and result.status == "error":
                print(f"      Error: {result.error_message}")

        b2_ok = sum(1 for r in results2 if r.status == "dry_run")
        b2_err = sum(1 for r in results2 if r.status == "error")
        b2_dup = sum(1 for r in results2 if r.status == "duplicate")
        print(f"\n  Results: {b2_ok} dry_run, {b2_err} errors, {b2_dup} duplicates")

        slack.send_success_summary(
            created_count=0,
            failed_count=b2_err,
            skipped_count=b2_ok,
            duplicates_count=b2_dup
        )
    else:
        results2 = []
        batch2_time = 0

    # ── Final Summary ────────────────────────────────────────────────────
    all_results = results1 + results2
    total_ok = sum(1 for r in all_results if r.status == "dry_run")
    total_err = sum(1 for r in all_results if r.status == "error")
    total_dup = sum(1 for r in all_results if r.status == "duplicate")
    total_time = batch1_time + batch2_time

    print(f"\n{'=' * 70}")
    print(f"FINAL SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Total processed: {len(all_results)}")
    print(f"  ✅ Dry-run OK:  {total_ok}")
    print(f"  ❌ Errors:      {total_err}")
    print(f"  ⚠️ Duplicates:  {total_dup}")
    print(f"  ⏱️ Total time:  {total_time:.0f}s ({total_time/60:.1f} min)")
    print(f"  📊 Avg per res: {total_time/max(len(all_results),1):.1f}s")

    if total_err > 0:
        print(f"\n  ⚠️ {total_err} errors found — review above for details")
    else:
        print(f"\n  🟢 ALL {total_ok} RESERVATIONS PROCESSED SUCCESSFULLY")
        print(f"  System is READY FOR LIVE DEPLOYMENT")


if __name__ == "__main__":
    main()
