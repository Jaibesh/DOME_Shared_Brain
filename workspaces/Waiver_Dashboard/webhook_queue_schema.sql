-- webhook_queue_schema.sql: TripWorks Webhook Ingestion Queue
-- Run this in the Supabase SQL Editor for your project

CREATE TABLE public.pending_webhooks (
    id UUID DEFAULT extensions.uuid_generate_v4() PRIMARY KEY,
    
    -- Extracted for fast lookups (some payloads might miss this if malformed)
    tw_confirmation TEXT,
    
    -- MD5 Hash of the payload dictionary to mechanically prevent duplicate webhooks 
    -- from being processed twice in close succession
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
CREATE INDEX idx_pending_webhooks_status_created ON public.pending_webhooks(status, created_at ASC);

-- Index to quickly check for duplicate payload hashes
CREATE INDEX idx_pending_webhooks_hash ON public.pending_webhooks(payload_hash);
