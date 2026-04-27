-- Run this in your Supabase SQL Editor to create the staff_users table

CREATE TABLE IF NOT EXISTS public.staff_users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable RLS (Row Level Security) if desired, though we use the service key in the backend.
-- ALTER TABLE public.staff_users ENABLE ROW LEVEL SECURITY;
