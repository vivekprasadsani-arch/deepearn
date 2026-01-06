-- Supabase Schema for DeepEarn Bot

-- Drop existing tables (optional, but ensures clean slate)
-- DROP TABLE IF EXISTS site_phone_numbers CASCADE;
-- DROP TABLE IF EXISTS phone_numbers CASCADE;
-- DROP TABLE IF EXISTS accounts CASCADE;
-- DROP TABLE IF EXISTS sites CASCADE;
-- DROP TABLE IF EXISTS referral_codes CASCADE;
-- DROP TABLE IF EXISTS users CASCADE;
-- DROP TABLE IF EXISTS settings CASCADE;

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

-- Enable RLS and Add Policies (Matches mnit-backup style)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE referral_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE phone_numbers ENABLE ROW LEVEL SECURITY;
ALTER TABLE site_phone_numbers ENABLE ROW LEVEL SECURITY;
ALTER TABLE settings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all on users" ON users FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on referral_codes" ON referral_codes FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on sites" ON sites FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on accounts" ON accounts FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on phone_numbers" ON phone_numbers FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on site_phone_numbers" ON site_phone_numbers FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on settings" ON settings FOR ALL USING (true) WITH CHECK (true);

-- Insert initial sites if they don't exist
INSERT INTO sites (domain, user_display_name) 
VALUES 
('tdjdnsd.vip', 'Site 1'),
('darino.vip', 'Site 2'),
('valeno.vip', 'Site 3')
ON CONFLICT (domain) DO NOTHING;
