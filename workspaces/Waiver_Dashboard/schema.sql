-- schema.sql: Epic 4x4 Dashboard Supabase Schema

-- This maps the 53-column Google Sheet and ArrivalGuest Pydantic Model to Postgres.

-- Main table for all reservations
CREATE TABLE public.reservations (
    -- Identity
    tw_confirmation TEXT PRIMARY KEY,
    tw_order_id TEXT,
    guest_name TEXT NOT NULL,
    primary_rider TEXT,
    
    -- Activity Details
    booking_type TEXT,            -- "Tour" or "Rental"
    activity_name TEXT,
    vehicle_model TEXT,
    vehicle_qty INTEGER DEFAULT 1,
    party_size INTEGER DEFAULT 1,
    activity_date DATE,           -- Standard DATE format: YYYY-MM-DD
    activity_time TEXT,           -- Standard TEXT format: "8:00 AM"

    -- Epic Waivers
    epic_expected INTEGER DEFAULT 0,
    epic_complete INTEGER DEFAULT 0,
    epic_names TEXT[] DEFAULT '{}',

    -- Polaris Waivers
    polaris_expected INTEGER DEFAULT 0,
    polaris_complete INTEGER DEFAULT 0,
    polaris_names TEXT[] DEFAULT '{}',

    -- OHV Permits (Rentals)
    ohv_required BOOLEAN DEFAULT false,
    ohv_uploaded BOOLEAN DEFAULT false,
    ohv_expected INTEGER DEFAULT 0,
    ohv_complete INTEGER DEFAULT 0,
    ohv_permit_names TEXT[] DEFAULT '{}',
    ohv_file_path TEXT,           -- URL to the file in Supabase Storage

    -- Financials & Check-in
    deposit_status TEXT DEFAULT 'Due',
    amount_due DECIMAL(10,2) DEFAULT 0.0,
    amount_paid DECIMAL(10,2) DEFAULT 0.0,
    adventure_assure TEXT DEFAULT 'None',
    
    checked_in BOOLEAN DEFAULT false,
    checked_in_at TIMESTAMP WITH TIME ZONE,
    checked_in_by TEXT,

    -- Rental Status
    rental_return_time TEXT,
    rental_status TEXT,

    -- Links & Notes
    tw_link TEXT,
    mpwr_link TEXT,
    mpwr_number TEXT,
    mpwr_waiver_link TEXT,
    mpwr_waiver_qr_url TEXT,         -- Supabase Storage public URL to per-reservation QR code PNG
    customer_portal_link TEXT,
    notes TEXT,
    payment_notes TEXT,
    trip_method TEXT,

    -- Webhook Email for deduplication
    webhook_email TEXT,

    -- Audit timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for searching today's arrivals quickly
CREATE INDEX idx_reservations_activity_date ON public.reservations(activity_date);

-- Webhook Persistence Logs
CREATE TABLE public.webhook_logs (
    id UUID DEFAULT extensions.uuid_generate_v4() PRIMARY KEY,
    event_type TEXT,               -- "tw-waiver-complete"
    payload JSONB,                 -- The entire raw payload 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Note: Ensure you have manually created the `ohv_permits` Storage Bucket
-- and toggled it to 'Public' via the Supabase Dashboard!
