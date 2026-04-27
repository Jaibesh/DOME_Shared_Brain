import os
from dotenv import load_dotenv
from sheets import get_sheets_client, execute_with_backoff, log_secondary_state
from mpowr_creator_bot import MpowrCreatorBot
from data_mapper import build_customer_payloads_from_row

load_dotenv()

def run_backfill(start_row: int, end_row: int):
    print(f"Starting Historical Backfill for rows {start_row} to {end_row}")
    client = get_sheets_client()
    sheet = client.open_by_key(os.getenv("GOOGLE_SHEET_ID")).sheet1
    sec_sheet = client.open_by_key(os.getenv("SECONDARY_SHEET_ID")).sheet1
    
    records = execute_with_backoff(sheet.get_all_records, value_render_option="FORMATTED_VALUE")
    sec_records = execute_with_backoff(sec_sheet.get_all_records)
    processed_tws = {str(r.get("TW Confirmation", "")).strip().upper() for r in sec_records if r.get("TW Confirmation")}
    
    pending = []
    
    for idx, row in enumerate(records):
        r_index = idx + 2
        if r_index < start_row:
            continue
        if r_index > end_row:
            break
            
        first_name = str(row.get("First Name", "")).strip()
        last_name = str(row.get("Last Name", "")).strip()
        tw_conf_upper = str(row.get("TW Confirmation", "")).strip().upper()
        
        if not first_name or not last_name or not tw_conf_upper:
            continue
            
        # Ignore testing datasets explicitly
        if first_name.lower() == "jennifer" and last_name.lower() == "johnson":
            continue

        if tw_conf_upper in processed_tws:
            print(f"Row {r_index} ({tw_conf_upper}) is already in Secondary Track Sheet. Skipping.")
            continue
            
        row["_row_index"] = r_index
        row["_is_retry"] = False
        pending.append(row)
        
    print(f"Found {len(pending)} unprocessed rows in range {start_row}-{end_row}.")
    
    if not pending:
        print("Nothing to process.")
        return
        
    mapped_customers = []
    for row in pending:
        try:
            payloads = build_customer_payloads_from_row(row, row['_row_index'])
            if payloads:
                # Typically 1 row = 1 reservation payload, mapping directly
                mapped_customers.append(payloads[0])
        except Exception as e:
            print(f"Failed to map row {row['_row_index']}: {e}")
            
    if not mapped_customers:
        return
        
    bot = MpowrCreatorBot(
        email=os.getenv("MPOWR_EMAIL"),
        password=os.getenv("MPOWR_PASSWORD"),
        headless=os.getenv("CREATOR_HEADLESS", "true").lower() == "true",
        dry_run=os.getenv("DRY_RUN", "True").lower() == "true"
    )
    
    results = bot.create_batch(mapped_customers)
    
    for customer, result in zip(mapped_customers, results):
        tw_conf = customer.get("TW Confirmation", "").strip()
        if not tw_conf: continue
        
        if result.status == "success":
            conf_id = result.mpowr_conf_id
            if conf_id:
                status_str = "Complete"
            else:
                status_str = "Error"
                conf_id = "EXTRACTION_FAILED"
        elif result.status == "dry_run":
            status_str = "Complete (Dry Run)"
            conf_id = "DRY_RUN"
        elif result.status == "duplicate":
            status_str = "Duplicate"
            conf_id = result.mpowr_conf_id or "EXISTS"
        else:
            status_str = "Error"
            conf_id = "ERROR"
            
        log_secondary_state(tw_conf, status_str, conf_id, (status_str in ["Complete", "Duplicate"]))

if __name__ == "__main__":
    run_backfill(480, 526)
