-- webhook_update_cancel_schema.sql: TripWorks Webhook Ingestion Queues for Updates and Cancellations
-- Run this in the Supabase SQL Editor for your project

-- Cancel Webhooks Queue
CREATE TABLE public.cancel_webhooks (
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
    
    -- Number of retry attempts before failure
    retry_count INTEGER DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE
);

-- Index for the local MPOWR agent to quickly pull the oldest pending webhooks
CREATE INDEX idx_cancel_webhooks_status_created ON public.cancel_webhooks(status, created_at ASC);
-- Index to quickly check for duplicate payload hashes
CREATE INDEX idx_cancel_webhooks_hash ON public.cancel_webhooks(payload_hash);


-- Update Webhooks Queue
CREATE TABLE public.update_webhooks (
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
    
    -- Number of retry attempts before failure
    retry_count INTEGER DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE
);

-- Index for the local MPOWR agent to quickly pull the oldest pending webhooks
CREATE INDEX idx_update_webhooks_status_created ON public.update_webhooks(status, created_at ASC);
-- Index to quickly check for duplicate payload hashes
CREATE INDEX idx_update_webhooks_hash ON public.update_webhooks(payload_hash);
