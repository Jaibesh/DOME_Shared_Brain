"""
embed.py — Vector Embedding Generation & Supabase Push

Generates 768-dimensional vector embeddings using Ollama nomic-embed-text
and pushes the structured chunks + embeddings to Supabase pgvector.

Embedding runs locally (zero cost). Only the final insert goes to Supabase.
"""

import os
import sys
import json
import ollama
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

# Add parent dirs to path for shared imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from shared.supabase_helpers import get_supabase

EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

# Vehicle folder → Supabase vehicle ID cache
_vehicle_id_cache: dict[str, str] = {}


def get_vehicle_id(folder_name: str, vehicle_meta: dict) -> Optional[str]:
    """
    Look up the Supabase vehicle ID for a given folder/model.
    Caches results to avoid repeated queries.
    """
    if folder_name in _vehicle_id_cache:
        return _vehicle_id_cache[folder_name]
    
    sb = get_supabase()
    model_name = vehicle_meta.get("model_name", "")
    seat_config = vehicle_meta.get("seat_config", "")
    
    if not model_name:
        return None
    
    try:
        result = sb.table("vehicles").select("id").eq(
            "model_name", model_name
        ).eq(
            "seat_config", seat_config
        ).execute()
        
        if result.data:
            vehicle_id = result.data[0]["id"]
            _vehicle_id_cache[folder_name] = vehicle_id
            return vehicle_id
    except Exception as e:
        print(f"    ⚠️  Vehicle lookup failed for {model_name}: {e}")
    
    return None


def generate_embedding(text: str) -> list[float]:
    """
    Generate a 768-dim vector embedding using local Ollama nomic-embed-text.
    
    Args:
        text: Text to embed
        
    Returns:
        List of 768 floats
    """
    # Prepend "search_document:" prefix for nomic-embed-text (required for best results)
    prefixed = f"search_document: {text}"
    
    response = ollama.embed(
        model=EMBED_MODEL,
        input=prefixed,
    )
    
    return response["embeddings"][0]


def push_chunk_to_supabase(chunk, embedding: list[float], vehicle_id: Optional[str] = None):
    """
    Insert a single processed chunk with its embedding into Supabase.
    
    Args:
        chunk: ProcessedChunk object from process.py
        embedding: 768-dim vector from generate_embedding()
        vehicle_id: Optional UUID of the vehicle in Supabase
    """
    sb = get_supabase()
    
    row = {
        "vehicle_id": vehicle_id,
        "source_file": chunk.source_file,
        "source_folder": chunk.source_folder,
        "assembly_name": chunk.assembly_name,
        "content_type": chunk.content_type,
        "raw_text": chunk.raw_text[:10000] if chunk.raw_text else None,  # Cap field size
        "structured_text": chunk.structured_text[:10000] if chunk.structured_text else None,
        "part_numbers": chunk.part_numbers if chunk.part_numbers else [],
        "page_number": chunk.page_number,
        "chunk_index": 0,
        "embedding": embedding,
        "metadata": chunk.metadata,
    }
    
    result = sb.table("document_chunks").insert(row).execute()
    return result


def push_parts_to_catalog(parts: list[dict], assembly_name: str, vehicle_meta: dict):
    """
    Insert extracted part numbers into the parts_catalog table.
    Skips duplicates (part_number is UNIQUE).
    
    Args:
        parts: List of part dicts from process.py
        assembly_name: Assembly name for this parts group
        vehicle_meta: Vehicle metadata for model association
    """
    if not parts:
        return
    
    sb = get_supabase()
    model_name = vehicle_meta.get("model_name", "Unknown")
    
    for part in parts:
        pn = str(part.get("number", "")).strip()
        if not pn or len(pn) < 5:  # Skip invalid/short numbers
            continue
        
        row = {
            "part_number": pn,
            "description": part.get("description", "Unknown"),
            "assembly_name": assembly_name,
            "vehicle_models": [model_name],
            "metadata": {
                "qty": part.get("qty", 1),
                "ref": part.get("ref"),
            },
        }
        
        try:
            # Upsert: insert or update if part number already exists
            sb.table("parts_catalog").upsert(
                row,
                on_conflict="part_number",
            ).execute()
        except Exception as e:
            # Skip duplicates silently
            if "duplicate" not in str(e).lower():
                print(f"    ⚠️  Failed to insert part {pn}: {e}")


def embed_and_push(chunks: list, batch_size: int = 5) -> dict:
    """
    Generate embeddings for all chunks and push to Supabase.
    
    Args:
        chunks: List of ProcessedChunk objects
        batch_size: Number of parts catalog updates per batch log
        
    Returns:
        Summary dict with counts
    """
    total = len(chunks)
    embedded = 0
    failed = 0
    parts_found = 0
    
    print(f"\n{'=' * 70}")
    print(f"Embedding & pushing {total} chunks to Supabase...")
    print(f"{'=' * 70}")
    
    for i, chunk in enumerate(chunks):
        prefix = f"  [{i+1}/{total}]"
        
        try:
            # Look up vehicle ID
            vehicle_id = get_vehicle_id(chunk.source_folder, chunk.vehicle_meta)
            
            # Generate embedding from the structured text
            text_to_embed = chunk.structured_text or chunk.raw_text
            if not text_to_embed or len(text_to_embed.strip()) < 20:
                print(f"{prefix} ⏭️  Skipping (text too short)")
                continue
            
            embedding = generate_embedding(text_to_embed)
            
            # Push to Supabase
            push_chunk_to_supabase(chunk, embedding, vehicle_id)
            embedded += 1
            
            # Push part numbers to catalog
            if chunk.part_numbers:
                push_parts_to_catalog(chunk.part_numbers, chunk.assembly_name, chunk.vehicle_meta)
                parts_found += len(chunk.part_numbers)
            
            print(f"{prefix} ✅ {chunk.assembly_name[:45]:45s} p{chunk.page_number} → embedded ({len(chunk.part_numbers)} parts)")
            
        except Exception as e:
            failed += 1
            print(f"{prefix} ❌ Failed: {e}")
    
    summary = {
        "total_chunks": total,
        "embedded": embedded,
        "failed": failed,
        "parts_cataloged": parts_found,
    }
    
    print(f"\n{'=' * 70}")
    print(f"✅ Embedding complete!")
    print(f"   Chunks embedded:  {embedded}/{total}")
    print(f"   Failed:           {failed}")
    print(f"   Parts cataloged:  {parts_found}")
    print(f"{'=' * 70}")
    
    return summary


def search_similar(query: str, vehicle_id: str = None, top_k: int = 5) -> list[dict]:
    """
    Search for similar documents using vector similarity.
    
    Args:
        query: Natural language search query
        vehicle_id: Optional UUID to filter by vehicle
        top_k: Number of results to return
        
    Returns:
        List of matching document chunks with similarity scores
    """
    # Embed the query (use "search_query:" prefix for nomic)
    response = ollama.embed(
        model=EMBED_MODEL,
        input=f"search_query: {query}",
    )
    query_embedding = response["embeddings"][0]
    
    sb = get_supabase()
    
    # Call the match_documents RPC function
    result = sb.rpc("match_documents", {
        "query_embedding": query_embedding,
        "match_threshold": 0.5,
        "match_count": top_k,
        "filter_vehicle_id": vehicle_id,
    }).execute()
    
    return result.data if result.data else []


# ── CLI entry point for testing search ─────────────────────────────

if __name__ == "__main__":
    print("RZR AutoParts AI — Vector Search Test")
    print("=" * 50)
    
    query = input("\nEnter search query (e.g., 'front brake caliper'): ").strip()
    if not query:
        query = "front brake caliper replacement"
    
    print(f"\n🔍 Searching for: '{query}'\n")
    
    results = search_similar(query, top_k=5)
    
    if not results:
        print("❌ No results found. Have you run the ingestion pipeline yet?")
    else:
        for i, r in enumerate(results):
            print(f"\n--- Result {i+1} (similarity: {r['similarity']:.3f}) ---")
            print(f"Assembly: {r['assembly_name']}")
            print(f"Source:   {r['source_file']}")
            print(f"Type:     {r['content_type']}")
            if r.get("structured_text"):
                print(f"Preview:  {r['structured_text'][:200]}...")
            if r.get("part_numbers"):
                print(f"Parts:    {json.dumps(r['part_numbers'][:3], indent=2)}")
