-- Supabase Schema for DeepEarn Bot

-- Users table
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    approved INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Referral codes table
CREATE TABLE IF NOT EXISTS referral_codes (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Sites table
CREATE TABLE IF NOT EXISTS sites (
    domain TEXT PRIMARY KEY,
    user_display_name TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Accounts table
CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    email TEXT,
    password TEXT,
    phone_number TEXT,
    referral_code TEXT,
    domain TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    login_status TEXT DEFAULT 'pending'
);

-- Phone numbers table
CREATE TABLE IF NOT EXISTS phone_numbers (
    phone_number TEXT PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Site-specific Phone numbers table
CREATE TABLE IF NOT EXISTS site_phone_numbers (
    phone_number TEXT,
    domain TEXT,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (phone_number, domain)
);

-- Global Settings table
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Insert initial sites if they don't exist
INSERT INTO sites (domain, user_display_name) 
VALUES 
('tdjdnsd.vip', 'Site 1'),
('darino.vip', 'Site 2'),
('valeno.vip', 'Site 3')
ON CONFLICT (domain) DO NOTHING;
