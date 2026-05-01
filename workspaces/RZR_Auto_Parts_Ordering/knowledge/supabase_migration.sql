-- ============================================================
-- RZR AutoParts AI — Supabase Schema Migration
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor)
-- ============================================================

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Vehicles table — the 5 fleet models
CREATE TABLE IF NOT EXISTS vehicles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name TEXT NOT NULL,            -- 'RZR Pro R', 'RZR Pro S', 'RZR XP S'
    model_year INTEGER NOT NULL DEFAULT 2026,
    seat_config TEXT NOT NULL,           -- '2-seat', '4-seat'
    trim_level TEXT NOT NULL DEFAULT 'Ultimate',
    color TEXT,                          -- 'Indy Red', 'Warm Grey', 'Stealth Grey'
    polaris_model_code TEXT,             -- e.g. 'Z26SPD92AN_AH_BN_BH'
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Seed the 5 fleet vehicles
INSERT INTO vehicles (model_name, seat_config, color, polaris_model_code) VALUES
    ('RZR Pro R', '2-seat', 'Indy Red', NULL),
    ('RZR Pro S', '2-seat', 'Warm Grey', 'Z26SPD92AN_AH_BN_BH'),
    ('RZR Pro S', '4-seat', 'Warm Grey', 'Z26SPD92AN_AH_BN_BH'),
    ('RZR XP S', '2-seat', 'Stealth Grey', 'Z26NEY99A4_B4_A6_B6'),
    ('RZR XP S', '4-seat', 'Stealth Grey', 'Z26NMY99A4_B4_A6_B6')
ON CONFLICT DO NOTHING;

-- 3. Document chunks — extracted and structured text from PDFs
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id UUID REFERENCES vehicles(id),
    source_file TEXT NOT NULL,           -- original PDF filename
    source_folder TEXT NOT NULL,         -- 'Pro R', 'Pro S4', etc.
    assembly_name TEXT,                  -- 'BRAKES, CALIPER, FRONT', etc.
    content_type TEXT NOT NULL DEFAULT 'text',  -- 'text', 'schematic', 'table', 'maintenance'
    raw_text TEXT,                       -- raw extracted text from PDF
    structured_text TEXT,                -- cleaned/structured text from Ollama
    part_numbers JSONB DEFAULT '[]',     -- extracted part numbers [{number, description, qty}]
    page_number INTEGER,
    chunk_index INTEGER DEFAULT 0,       -- chunk position within a document
    embedding vector(768),               -- nomic-embed-text produces 768-dim vectors
    metadata JSONB DEFAULT '{}',         -- flexible metadata storage
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 4. Parts catalog — individual OEM parts
CREATE TABLE IF NOT EXISTS parts_catalog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    part_number TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    assembly_name TEXT,                  -- which assembly this part belongs to
    vehicle_models TEXT[] DEFAULT '{}',  -- which models this part fits
    price_cents INTEGER,                 -- price in cents (e.g. 28999 = $289.99)
    superseded_by TEXT,                  -- if this part number has been replaced
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 5. Indexes for fast retrieval
-- HNSW index on embeddings for vector similarity search
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
    ON document_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Standard indexes for filtering
CREATE INDEX IF NOT EXISTS idx_document_chunks_vehicle
    ON document_chunks(vehicle_id);

CREATE INDEX IF NOT EXISTS idx_document_chunks_assembly
    ON document_chunks(assembly_name);

CREATE INDEX IF NOT EXISTS idx_document_chunks_content_type
    ON document_chunks(content_type);

CREATE INDEX IF NOT EXISTS idx_parts_catalog_part_number
    ON parts_catalog(part_number);

CREATE INDEX IF NOT EXISTS idx_parts_catalog_assembly
    ON parts_catalog(assembly_name);

-- 6. Function for vector similarity search
CREATE OR REPLACE FUNCTION match_documents(
    query_embedding vector(768),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 10,
    filter_vehicle_id UUID DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    vehicle_id UUID,
    source_file TEXT,
    assembly_name TEXT,
    content_type TEXT,
    structured_text TEXT,
    part_numbers JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        dc.id,
        dc.vehicle_id,
        dc.source_file,
        dc.assembly_name,
        dc.content_type,
        dc.structured_text,
        dc.part_numbers,
        1 - (dc.embedding <=> query_embedding) AS similarity
    FROM document_chunks dc
    WHERE
        dc.embedding IS NOT NULL
        AND 1 - (dc.embedding <=> query_embedding) > match_threshold
        AND (filter_vehicle_id IS NULL OR dc.vehicle_id = filter_vehicle_id)
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
