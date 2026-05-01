"""
process.py — Ollama-Powered Text Structuring

Takes raw extracted PDF text and uses the local phi4 model to:
1. Clean and reformat chaotic PDF text into clean Markdown
2. Extract part numbers into structured JSON arrays
3. Identify repair procedures, torque specs, and warnings

Zero API cost — runs entirely on local Ollama.
"""

import os
import re
import json
import ollama
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

TEXT_MODEL = os.getenv("OLLAMA_TEXT_MODEL", "phi4")


@dataclass
class ProcessedChunk:
    """A structured chunk ready for embedding."""
    source_file: str
    source_folder: str
    assembly_name: str
    content_type: str
    page_number: int
    raw_text: str
    structured_text: str
    part_numbers: list = field(default_factory=list)
    vehicle_meta: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


# ── Prompts ───────────────────────────────────────────────────────

STRUCTURING_PROMPT = """You are a technical document processor for Polaris RZR off-road vehicle service manuals and parts catalogs.

Your job is to take raw, messy text extracted from a PDF and reformat it into clean, structured Markdown.

RULES:
1. Preserve ALL technical information exactly — part numbers, torque specs, measurements, warnings.
2. Fix formatting issues: broken lines, merged words, random whitespace.
3. Organize into logical sections using Markdown headers (##, ###).
4. Format part lists as Markdown tables with columns: | Ref# | Part Number | Description | Qty |
5. Highlight any WARNING, CAUTION, or NOTE blocks using > blockquotes.
6. Do NOT add any information that is not in the original text.
7. Do NOT explain what you're doing — just output the cleaned document.

The assembly category is: {assembly_name}
The vehicle is: {vehicle_info}

RAW TEXT:
{raw_text}

OUTPUT (clean Markdown only):"""


PART_EXTRACTION_PROMPT = """Extract ALL part numbers from this text. A Polaris part number is typically a 7-digit number (e.g., 1334441, 5412189, 7042430).

Return ONLY a JSON array. Each item must have:
- "number": the part number string
- "description": what the part is (from the text)
- "qty": quantity if mentioned, otherwise 1
- "ref": reference number if present, otherwise null

If no part numbers are found, return an empty array: []

TEXT:
{text}

JSON ARRAY:"""


def structure_text(raw_text: str, assembly_name: str, vehicle_meta: dict) -> str:
    """
    Use Ollama phi4 to clean and structure raw PDF text into Markdown.
    
    Args:
        raw_text: Raw text extracted from PDF
        assembly_name: Name of the assembly (e.g., "BRAKES, CALIPER, FRONT")
        vehicle_meta: Vehicle metadata dict
        
    Returns:
        Clean, structured Markdown text
    """
    # Skip very short or empty text
    if not raw_text or len(raw_text.strip()) < 50:
        return raw_text.strip() if raw_text else ""
    
    vehicle_info = f"{vehicle_meta.get('model_name', 'Unknown')} {vehicle_meta.get('seat_config', '')}"
    
    prompt = STRUCTURING_PROMPT.format(
        assembly_name=assembly_name,
        vehicle_info=vehicle_info,
        raw_text=raw_text[:8000],  # Cap input to avoid context overflow
    )
    
    try:
        response = ollama.chat(
            model=TEXT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": 0.1,      # Near-deterministic for accuracy
                "num_predict": 4096,     # Allow long outputs for parts tables
                "top_p": 0.9,
            },
        )
        return response["message"]["content"].strip()
    except Exception as e:
        print(f"    ⚠️  Ollama structuring failed: {e}")
        return raw_text.strip()


def extract_part_numbers(text: str) -> list[dict]:
    """
    Use Ollama phi4 to extract part numbers from text into structured JSON.
    
    Also runs a regex fallback to catch any parts the LLM might miss.
    
    Args:
        text: Text to extract part numbers from
        
    Returns:
        List of dicts with keys: number, description, qty, ref
    """
    parts = []
    
    # ── Strategy 1: Regex extraction (fast, reliable baseline) ──
    # Polaris part numbers are typically 7 digits
    regex_parts = set(re.findall(r'\b(\d{7})\b', text))
    
    # ── Strategy 2: LLM extraction (understands context) ──
    if len(text.strip()) > 100:
        prompt = PART_EXTRACTION_PROMPT.format(text=text[:6000])
        
        try:
            response = ollama.chat(
                model=TEXT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={
                    "temperature": 0.0,
                    "num_predict": 2048,
                },
                format="json",
            )
            
            content = response["message"]["content"].strip()
            
            # Parse the JSON response
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    parts = parsed
                elif isinstance(parsed, dict) and "parts" in parsed:
                    parts = parsed["parts"]
            except json.JSONDecodeError:
                # Try to extract JSON array from the response
                match = re.search(r'\[.*\]', content, re.DOTALL)
                if match:
                    try:
                        parts = json.loads(match.group())
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            print(f"    ⚠️  Ollama part extraction failed: {e}")
    
    # ── Merge: Add any regex-found parts not in LLM results ──
    llm_numbers = {str(p.get("number", "")) for p in parts}
    for pn in regex_parts:
        if pn not in llm_numbers:
            parts.append({
                "number": pn,
                "description": "Unknown (regex-detected)",
                "qty": 1,
                "ref": None,
            })
    
    return parts


def process_pages(pages: list, skip_structuring: bool = False) -> list[ProcessedChunk]:
    """
    Process a list of ExtractedPage objects through the Ollama pipeline.
    
    Args:
        pages: List of ExtractedPage objects from extract.py
        skip_structuring: If True, skip LLM structuring (useful for testing)
        
    Returns:
        List of ProcessedChunk objects ready for embedding
    """
    chunks = []
    total = len(pages)
    
    for i, page in enumerate(pages):
        prefix = f"  [{i+1}/{total}]"
        
        # Skip pages with no meaningful text
        if not page.raw_text or len(page.raw_text.strip()) < 30:
            print(f"{prefix} ⏭️  Skipping empty page (p{page.page_number})")
            continue
        
        assembly = page.assembly_name
        print(f"{prefix} 🔧 {assembly[:50]:50s} p{page.page_number} ({page.content_type})", end="", flush=True)
        
        # Structure the text with Ollama
        if skip_structuring:
            structured = page.raw_text.strip()
        else:
            structured = structure_text(page.raw_text, assembly, page.vehicle_meta)
        
        # Extract part numbers (from structured text for better accuracy)
        source_for_parts = structured if structured else page.raw_text
        part_numbers = extract_part_numbers(source_for_parts)
        
        print(f" → {len(part_numbers)} parts found")
        
        chunk = ProcessedChunk(
            source_file=page.source_file,
            source_folder=page.source_folder,
            assembly_name=assembly,
            content_type=page.content_type,
            page_number=page.page_number,
            raw_text=page.raw_text,
            structured_text=structured,
            part_numbers=part_numbers,
            vehicle_meta=page.vehicle_meta,
            metadata={
                "has_images": page.has_images,
                "image_paths": page.image_paths,
                "text_length": len(page.raw_text),
            },
        )
        chunks.append(chunk)
    
    return chunks


# ── CLI entry point for standalone testing ─────────────────────────

if __name__ == "__main__":
    # Quick test: process a single hardcoded text sample
    test_text = """
    BRAKES, CALIPER, FRONT
    Ref Part Number    Description         Qty
    1   1912375        Caliper Asm., Front  1
    2   1911888        Brake Pad Kit        1
    3   7080693        Bolt, Hex Flange     2
    4   5412189        Pin, Caliper Slide   2
    WARNING: Always replace brake pads in pairs.
    Torque: Caliper mounting bolts to 35 ft-lbs (47 Nm)
    """
    
    print("Testing Ollama text structuring...")
    structured = structure_text(test_text, "BRAKES, CALIPER, FRONT", {"model_name": "RZR Pro S"})
    print(f"\n--- Structured Output ---\n{structured}\n")
    
    print("Testing part number extraction...")
    parts = extract_part_numbers(test_text)
    print(f"\n--- Extracted Parts ---\n{json.dumps(parts, indent=2)}")
