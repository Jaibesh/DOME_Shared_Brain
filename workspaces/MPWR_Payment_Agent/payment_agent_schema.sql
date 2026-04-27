-- payment_agent_schema.sql
-- Run this in your Supabase SQL Editor to prepare for the MPWR Payment Agent

-- 1. Create a dedicated table for payment webhooks
CREATE TABLE public.pending_payment_webhooks (
    id UUID DEFAULT extensions.uuid_generate_v4() PRIMARY KEY,
    
    -- Extracted for fast lookups
    tw_confirmation TEXT,
    
    -- MD5 Hash of the payload dictionary to mechanically prevent duplicate webhooks 
    payload_hash TEXT,
    
    -- The raw HTTP data
    headers JSONB,
    payload JSONB,
    
    -- Queue State: 'pending', 'processed', 'retry', 'failed'
    status TEXT DEFAULT 'pending',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE
);

-- Index for the local MPOWR agent to quickly pull the oldest pending webhooks
CREATE INDEX idx_pending_payment_webhooks_status_created ON public.pending_payment_webhooks(status, created_at ASC);

-- Index to quickly check for duplicate payload hashes
CREATE INDEX idx_pending_payment_webhooks_hash ON public.pending_payment_webhooks(payload_hash);


-- 2. Add column to track MPOWR settlement status in the main reservations table
-- Using IF NOT EXISTS is safe in Postgres 14+ when adding columns, but for standard we just run it.
ALTER TABLE public.reservations 
ADD COLUMN IF NOT EXISTS mpwr_payment_settled BOOLEAN DEFAULT false;

-- Add an index for faster deposit/payment checking queries
CREATE INDEX IF NOT EXISTS idx_reservations_deposit_status ON public.reservations(deposit_status);
CREATE INDEX IF NOT EXISTS idx_reservations_mpwr_payment_settled ON public.reservations(mpwr_payment_settled);
