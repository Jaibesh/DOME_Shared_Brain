"""
extract.py — PDF Image Extraction & Vision-Based OCR using PyMuPDF + Ollama

The Polaris parts catalog PDFs are image-only (no selectable text).
This module:
1. Extracts full-page images from each PDF using PyMuPDF
2. Sends each image to Ollama's llama3.2-vision for OCR + structured extraction
3. Returns structured data with part numbers, descriptions, and assembly context

Processing is 100% local via Ollama — zero API cost.
"""

import os
import re
import io
import json
import base64
import fitz  # PyMuPDF
import ollama
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llama3.2-vision")


# ── Map folder names to vehicle metadata ──────────────────────────

FOLDER_VEHICLE_MAP = {
    "Pro R": {
        "model_name": "RZR Pro R",
        "seat_config": "2-seat",
        "color": "Indy Red",
    },
    "Pro S Ultimate": {
        "model_name": "RZR Pro S",
        "seat_config": "2-seat",
        "color": "Warm Grey",
    },
    "Pro S4": {
        "model_name": "RZR Pro S",
        "seat_config": "4-seat",
        "color": "Warm Grey",
    },
    "XPS2 Ultimate": {
        "model_name": "RZR XP S",
        "seat_config": "2-seat",
        "color": "Stealth Grey",
    },
    "XPS4": {
        "model_name": "RZR XP S",
        "seat_config": "4-seat",
        "color": "Stealth Grey",
    },
}


@dataclass
class ExtractedPage:
    """Represents a single extracted page from a PDF."""
    source_file: str
    source_folder: str
    assembly_name: str
    page_number: int
    raw_text: str
    has_images: bool
    image_path: str = ""
    content_type: str = "text"
    vehicle_meta: dict = field(default_factory=dict)
    part_numbers: list = field(default_factory=list)


def parse_assembly_name(filename: str) -> str:
    """
    Extract the assembly name from a PDF filename.

    Handles two formats:
    1. Clean: "BRAKES, CALIPER, FRONT.pdf"
    2. URL-encoded: "parts.polarisind.com_PrintAssembly...AssemblyName=BODY, DASH..."
    """
    name = Path(filename).stem

    # Handle URL-encoded filenames from parts.polarisind.com
    if "AssemblyName=" in name:
        match = re.search(r"AssemblyName=([^&]+)", name)
        if match:
            assembly = match.group(1)
            # Remove surrounding underscores used as separators
            assembly = assembly.replace("_", " ").strip()
            # Clean up the model code suffix
            assembly = re.split(r"\s*-\s*Z\d", assembly)[0].strip()
            # Remove trailing assembly codes like "(C750235)"
            assembly = re.sub(r"\s*\([A-Z0-9\-]+\)\s*$", "", assembly).strip()
            return assembly

    # Handle service manual
    if "service manual" in name.lower():
        return "SERVICE MANUAL"

    # Handle maintenance pages
    if "SERVICE & MAINTENANCE" in name.upper() or "MAINTENANCE PAGE" in name.upper():
        return "SERVICE & MAINTENANCE"

    return name.strip()


# ── Vision OCR Prompts ────────────────────────────────────────────

SCHEMATIC_PROMPT = """You are analyzing an exploded parts diagram from a Polaris RZR service manual.
This image shows a {assembly_name} assembly for a 2026 {vehicle_name}.

Extract ALL information visible in this image. Provide:

1. A description of what this assembly/diagram shows
2. ALL part numbers and their descriptions in a Markdown table:
   | Ref | Part Number | Description | Qty |
3. Any notes, warnings, or torque specifications visible

Be thorough — extract EVERY part number visible. Part numbers are typically 7-digit numbers.
Output clean Markdown only. Do NOT add information that isn't in the image."""

PARTS_TABLE_PROMPT = """You are reading a parts list table from a Polaris RZR service manual.
This is the {assembly_name} parts table for a 2026 {vehicle_name}.

Extract ALL rows from this parts table into a Markdown table with columns:
| Ref | Part Number | Description | Qty | Notes |

Be extremely precise with part numbers — they are typically 7 digits.
Include EVERY row visible in the table. Output Markdown only."""


def render_page_to_image(doc: fitz.Document, page_num: int, output_dir: str,
                         assembly_name: str, dpi: int = 200) -> str:
    """
    Render a PDF page to a PNG image file.

    Args:
        doc: PyMuPDF document
        page_num: Page number (0-indexed)
        output_dir: Directory to save images
        assembly_name: Assembly name for the filename
        dpi: Resolution (200 is good balance of quality vs file size)

    Returns:
        Path to the saved image file
    """
    page = doc[page_num]
    zoom = dpi / 72  # 72 is the default PDF DPI
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)

    os.makedirs(output_dir, exist_ok=True)
    safe_name = re.sub(r'[^\w\-]', '_', assembly_name)[:50]
    img_path = os.path.join(output_dir, f"{safe_name}_p{page_num + 1}.png")

    pix.save(img_path)
    return img_path


def ocr_image_with_vision(image_path: str, assembly_name: str,
                          vehicle_name: str, is_schematic: bool = True) -> str:
    """
    Send an image to Ollama llama3.2-vision for OCR extraction.

    Args:
        image_path: Path to the PNG image
        assembly_name: Name of the assembly for context
        vehicle_name: Vehicle model name for context
        is_schematic: Whether this is a diagram (True) or parts table (False)

    Returns:
        Structured Markdown text from the vision model
    """
    prompt = SCHEMATIC_PROMPT if is_schematic else PARTS_TABLE_PROMPT
    prompt = prompt.format(
        assembly_name=assembly_name,
        vehicle_name=vehicle_name,
    )

    try:
        response = ollama.chat(
            model=VISION_MODEL,
            messages=[{
                "role": "user",
                "content": prompt,
                "images": [image_path],
            }],
            options={
                "temperature": 0.1,
                "num_predict": 4096,
            },
        )
        return response["message"]["content"].strip()
    except Exception as e:
        print(f"    [!] Vision OCR failed: {e}")
        return ""


def extract_part_numbers_from_text(text: str) -> list[dict]:
    """Extract part numbers from OCR'd text using regex."""
    parts = []
    seen = set()

    # Match 7-digit part numbers
    for match in re.finditer(r'\b(\d{7})\b', text):
        pn = match.group(1)
        if pn not in seen:
            seen.add(pn)
            parts.append({
                "number": pn,
                "description": "Extracted from OCR",
                "qty": 1,
                "ref": None,
            })

    # Try to match table rows: | ref | part_number | description | qty |
    table_pattern = r'\|\s*(\d+)\s*\|\s*(\d{7})\s*\|\s*([^|]+)\|\s*(\d+)\s*\|'
    for match in re.finditer(table_pattern, text):
        ref, pn, desc, qty = match.groups()
        if pn not in seen:
            seen.add(pn)
        # Update description if we find a table match
        for p in parts:
            if p["number"] == pn:
                p["description"] = desc.strip()
                p["qty"] = int(qty)
                p["ref"] = ref
                break
        else:
            parts.append({
                "number": pn,
                "description": desc.strip(),
                "qty": int(qty),
                "ref": ref,
            })

    return parts


def classify_page(doc: fitz.Document, page_num: int, assembly_name: str) -> str:
    """Classify a page as schematic, table, or other based on heuristics."""
    page = doc[page_num]
    text = page.get_text("text").strip()
    images = page.get_images(full=True)

    name_lower = assembly_name.lower()
    if "maintenance" in name_lower or "service &" in name_lower:
        return "maintenance"

    # If there are images and minimal text, it's a schematic/diagram
    if images and len(text) < 100:
        return "schematic"

    # If there's substantial text, it's a text/table page
    if len(text) > 100:
        return "table"

    # Default for image-only pages
    if images:
        return "schematic"

    return "text"


def extract_pdf(pdf_path: str, folder_name: str, output_dir: str,
                use_vision: bool = True) -> list[ExtractedPage]:
    """
    Extract all pages from a PDF, rendering to images and running vision OCR.

    Args:
        pdf_path: Full path to the PDF
        folder_name: Parent folder name (for vehicle mapping)
        output_dir: Directory for rendered images
        use_vision: If True, run Ollama vision OCR on each page

    Returns:
        List of ExtractedPage objects
    """
    filename = os.path.basename(pdf_path)
    assembly_name = parse_assembly_name(filename)
    vehicle_meta = FOLDER_VEHICLE_MAP.get(folder_name, {})
    vehicle_name = f"{vehicle_meta.get('model_name', 'RZR')} {vehicle_meta.get('seat_config', '')}"

    pages = []

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"  [!] Failed to open {filename}: {e}")
        return pages

    img_dir = os.path.join(output_dir, "images", folder_name)

    for page_num in range(len(doc)):
        content_type = classify_page(doc, page_num, assembly_name)

        # Render page to image
        image_path = render_page_to_image(doc, page_num, img_dir, assembly_name)

        # Run vision OCR if enabled
        raw_text = ""
        part_numbers = []

        if use_vision:
            is_schematic = content_type == "schematic"
            raw_text = ocr_image_with_vision(
                image_path, assembly_name, vehicle_name, is_schematic
            )
            part_numbers = extract_part_numbers_from_text(raw_text)

        extracted = ExtractedPage(
            source_file=filename,
            source_folder=folder_name,
            assembly_name=assembly_name,
            page_number=page_num + 1,
            raw_text=raw_text,
            has_images=True,
            image_path=image_path,
            content_type=content_type,
            vehicle_meta=vehicle_meta,
            part_numbers=part_numbers,
        )
        pages.append(extracted)

    doc.close()
    return pages


def extract_all(docs_dir: str, output_dir: str,
                use_vision: bool = True) -> list[ExtractedPage]:
    """
    Extract all PDFs from the Vehicle_Documentation directory.

    Args:
        docs_dir: Path to the Vehicle_Documentation folder
        output_dir: Directory for rendered images and logs
        use_vision: If True, run Ollama vision OCR

    Returns:
        List of all ExtractedPage objects
    """
    all_pages = []

    for folder_name in sorted(os.listdir(docs_dir)):
        folder_path = os.path.join(docs_dir, folder_name)
        if not os.path.isdir(folder_path):
            continue

        if folder_name not in FOLDER_VEHICLE_MAP:
            print(f"  [!] Skipping unknown folder: {folder_name}")
            continue

        # Get all PDFs (including in subdirectories)
        pdf_files = []
        for root, dirs, files in os.walk(folder_path):
            for f in files:
                if f.lower().endswith(".pdf"):
                    pdf_files.append(os.path.join(root, f))

        vehicle_info = FOLDER_VEHICLE_MAP[folder_name]
        print(f"\n[FOLDER] {folder_name} ({vehicle_info['model_name']} {vehicle_info['seat_config']}) -- {len(pdf_files)} PDFs")

        for pdf_path in sorted(pdf_files):
            fname = os.path.basename(pdf_path)
            assembly = parse_assembly_name(fname)
            print(f"  >> {assembly[:60]:60s}", end="", flush=True)

            pages = extract_pdf(pdf_path, folder_name, output_dir, use_vision)

            if pages:
                parts_count = sum(len(p.part_numbers) for p in pages)
                print(f" | {len(pages)} pages | {parts_count} parts")
            else:
                print(f" | EMPTY")

            all_pages.extend(pages)

    return all_pages


# ── CLI entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Extract PDFs with Vision OCR")
    parser.add_argument("--folder", type=str, default=None, help="Process only this folder")
    parser.add_argument("--no-vision", action="store_true", help="Skip vision OCR (just render images)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of PDFs to process")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs_dir = os.path.join(base_dir, "Vehicle_Documentation")
    output_dir = os.path.join(base_dir, "knowledge", "_output")

    if not os.path.exists(docs_dir):
        print(f"[!] Vehicle_Documentation not found at {docs_dir}")
        sys.exit(1)

    print("=" * 70)
    print("RZR AutoParts AI -- PDF Extraction Pipeline (Vision OCR)")
    print("=" * 70)

    use_vision = not args.no_vision

    if args.folder:
        folder_path = os.path.join(docs_dir, args.folder)
        if not os.path.exists(folder_path):
            print(f"[!] Folder not found: {args.folder}")
            sys.exit(1)

        pdf_files = sorted([
            os.path.join(folder_path, f)
            for f in os.listdir(folder_path)
            if f.lower().endswith(".pdf")
        ])

        if args.limit:
            pdf_files = pdf_files[:args.limit]

        all_pages = []
        for pdf_path in pdf_files:
            pages = extract_pdf(pdf_path, args.folder, output_dir, use_vision)
            all_pages.extend(pages)
    else:
        all_pages = extract_all(docs_dir, output_dir, use_vision)

    print(f"\n{'=' * 70}")
    print(f"Extraction complete!")
    print(f"  Total pages: {len(all_pages)}")
    print(f"  With text:   {sum(1 for p in all_pages if p.raw_text):,}")
    print(f"  Total parts: {sum(len(p.part_numbers) for p in all_pages):,}")

    # Save summary
    os.makedirs(output_dir, exist_ok=True)
    summary_path = os.path.join(output_dir, "extraction_summary.json")
    summary = []
    for p in all_pages:
        summary.append({
            "file": p.source_file,
            "folder": p.source_folder,
            "assembly": p.assembly_name,
            "page": p.page_number,
            "type": p.content_type,
            "text_length": len(p.raw_text),
            "parts_found": len(p.part_numbers),
            "image_path": p.image_path,
            "preview": p.raw_text[:300] if p.raw_text else "",
        })

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"  Summary: {summary_path}")
