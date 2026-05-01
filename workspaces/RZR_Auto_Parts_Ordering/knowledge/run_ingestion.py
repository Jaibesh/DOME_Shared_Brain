"""
run_ingestion.py — Main CLI Orchestrator for Knowledge Ingestion

Orchestrates the full pipeline:
  1. Extract text/images from all PDFs (PyMuPDF — local)
  2. Structure text with Ollama phi4 (local)
  3. Generate embeddings with nomic-embed-text (local)
  4. Push to Supabase pgvector (remote)

Usage:
    # Full pipeline (all vehicles)
    python -m knowledge.run_ingestion

    # Single folder only (for testing)
    python -m knowledge.run_ingestion --folder "Pro R"

    # Extract only (no Ollama, no Supabase)
    python -m knowledge.run_ingestion --extract-only

    # Skip structuring (just extract → embed → push)
    python -m knowledge.run_ingestion --skip-structuring
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from knowledge.extract import extract_all, extract_pdf, FOLDER_VEHICLE_MAP
from knowledge.process import process_pages
from knowledge.embed import embed_and_push


def run_pipeline(
    docs_dir: str,
    output_dir: str,
    folder_filter: str = None,
    extract_only: bool = False,
    skip_structuring: bool = False,
):
    """
    Run the full ingestion pipeline.
    
    Args:
        docs_dir: Path to Vehicle_Documentation folder
        output_dir: Path to save extracted images and logs
        folder_filter: Optional — only process this folder (e.g., "Pro R")
        extract_only: If True, stop after extraction (no Ollama, no Supabase)
        skip_structuring: If True, skip Ollama text structuring (use raw text)
    """
    start_time = time.time()
    
    print("=" * 70)
    print("🔧 RZR AutoParts AI — Knowledge Ingestion Pipeline")
    print("=" * 70)
    print(f"  Docs directory:     {docs_dir}")
    print(f"  Output directory:   {output_dir}")
    print(f"  Folder filter:      {folder_filter or 'ALL'}")
    print(f"  Extract only:       {extract_only}")
    print(f"  Skip structuring:   {skip_structuring}")
    print("=" * 70)
    
    # ── Step 1: PDF Extraction ─────────────────────────────────────
    print(f"\n📄 STEP 1: Extracting PDFs...")
    
    if folder_filter:
        # Process a single folder
        folder_path = os.path.join(docs_dir, folder_filter)
        if not os.path.exists(folder_path):
            print(f"❌ Folder not found: {folder_path}")
            return
        
        pdf_files = [
            os.path.join(folder_path, f)
            for f in os.listdir(folder_path)
            if f.lower().endswith(".pdf")
        ]
        
        all_pages = []
        vehicle_info = FOLDER_VEHICLE_MAP.get(folder_filter, {})
        print(f"\n📁 {folder_filter} ({vehicle_info.get('model_name', '?')}) — {len(pdf_files)} PDFs")
        
        for pdf_path in sorted(pdf_files):
            pages = extract_pdf(pdf_path, folder_filter, output_dir)
            all_pages.extend(pages)
    else:
        all_pages = extract_all(docs_dir, output_dir)
    
    print(f"\n  ✅ Extracted {len(all_pages)} pages from PDFs")
    
    if extract_only:
        print(f"\n  ⏹️  Extract-only mode — stopping here.")
        _save_extraction_log(all_pages, output_dir)
        return
    
    # ── Step 2: Ollama Text Structuring ────────────────────────────
    print(f"\n🤖 STEP 2: Structuring text with Ollama ({os.getenv('OLLAMA_TEXT_MODEL', 'phi4')})...")
    
    chunks = process_pages(all_pages, skip_structuring=skip_structuring)
    print(f"\n  ✅ Processed {len(chunks)} chunks")
    
    # ── Step 3: Embed & Push to Supabase ───────────────────────────
    print(f"\n📊 STEP 3: Generating embeddings & pushing to Supabase...")
    
    summary = embed_and_push(chunks)
    
    # ── Summary ────────────────────────────────────────────────────
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    
    print(f"\n{'=' * 70}")
    print(f"🏁 PIPELINE COMPLETE — {minutes}m {seconds}s")
    print(f"{'=' * 70}")
    print(f"  Pages extracted:     {len(all_pages)}")
    print(f"  Chunks processed:    {len(chunks)}")
    print(f"  Chunks embedded:     {summary['embedded']}")
    print(f"  Parts cataloged:     {summary['parts_cataloged']}")
    print(f"  Failures:            {summary['failed']}")
    print(f"{'=' * 70}")
    
    # Save run log
    _save_run_log(all_pages, chunks, summary, elapsed, output_dir)


def _save_extraction_log(pages: list, output_dir: str):
    """Save extraction results for inspection."""
    os.makedirs(output_dir, exist_ok=True)
    log_path = os.path.join(output_dir, "extraction_log.json")
    
    log = []
    for p in pages:
        log.append({
            "file": p.source_file,
            "folder": p.source_folder,
            "assembly": p.assembly_name,
            "page": p.page_number,
            "type": p.content_type,
            "text_length": len(p.raw_text),
            "has_images": p.has_images,
            "preview": p.raw_text[:200] if p.raw_text else "",
        })
    
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
    
    print(f"  📝 Extraction log saved to: {log_path}")


def _save_run_log(pages, chunks, summary, elapsed, output_dir):
    """Save a full run log for auditing."""
    os.makedirs(output_dir, exist_ok=True)
    log_path = os.path.join(output_dir, "run_log.json")
    
    log = {
        "elapsed_seconds": round(elapsed, 1),
        "pages_extracted": len(pages),
        "chunks_processed": len(chunks),
        "summary": summary,
        "vehicles_processed": list(set(p.source_folder for p in pages)),
        "assemblies_processed": list(set(c.assembly_name for c in chunks)),
    }
    
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
    
    print(f"  📝 Run log saved to: {log_path}")


def main():
    parser = argparse.ArgumentParser(
        description="RZR AutoParts AI — Knowledge Ingestion Pipeline"
    )
    parser.add_argument(
        "--folder",
        type=str,
        default=None,
        help="Process only this folder (e.g., 'Pro R', 'Pro S4')"
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Only extract PDFs — no Ollama, no Supabase"
    )
    parser.add_argument(
        "--skip-structuring",
        action="store_true",
        help="Skip Ollama text structuring (use raw text for embedding)"
    )
    
    args = parser.parse_args()
    
    # Resolve paths
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs_dir = os.path.join(base_dir, "Vehicle_Documentation")
    output_dir = os.path.join(base_dir, "knowledge", "_output")
    
    if not os.path.exists(docs_dir):
        print(f"❌ Vehicle_Documentation folder not found at {docs_dir}")
        sys.exit(1)
    
    run_pipeline(
        docs_dir=docs_dir,
        output_dir=output_dir,
        folder_filter=args.folder,
        extract_only=args.extract_only,
        skip_structuring=args.skip_structuring,
    )


if __name__ == "__main__":
    main()
