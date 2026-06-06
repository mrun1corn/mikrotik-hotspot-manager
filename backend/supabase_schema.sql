-- Create the users table for MikroTik Hotspot Manager
create table users (
    username text primary key,
    phone text not null,
    package text not null,
    password text not null,
    screenshot_url text not null,
    registration_timestamp timestamp with time zone default timezone('utc'::text, now()) not null,
    approved boolean default false not null,
    approval_timestamp timestamp with time zone,
    expiration_timestamp timestamp with time zone,
    telegram_message_id bigint
);

-- Enable Row Level Security (RLS) if desired, or leave open for simple API access
alter table users enable row level security;

-- Create policy to allow all actions using service role, or select/insert policy for public/service role.
-- For a simple backend integration, since we access via the service_role key from Python, RLS policies are bypassed by default.
