# Vercel & Supabase Stateless Deployment Guide

This guide explains how to deploy the MikroTik Hotspot Manager on **Vercel** as a serverless application, using **Supabase** as the stateless database and storage backend.

## Architecture Overview

*   **Flask on Vercel**: Deployed as a stateless Serverless Function. No files are stored locally.
*   **Supabase Database**: Stores hotspot user metadata in a Postgres table.
*   **Supabase Storage**: Stores payment screenshot uploads in a public storage bucket.
*   **Telegram Webhooks**: Replaces long-polling. Telegram sends real-time updates directly to a `/api/webhook` endpoint on your Vercel deployment.
*   **Vercel Cron Jobs**: Replaces background threads. A scheduled cron hits `/api/cron/check-expiration` every 10 minutes to clean up expired users.

---

## Step 1: Configure Supabase

1.  **Create a Supabase Project**: Sign up at [supabase.com](https://supabase.com/) and create a new project.
2.  **Execute the SQL Schema**:
    *   Open your project dashboard.
    *   Go to **SQL Editor** in the left menu.
    *   Click **New Query**.
    *   Copy and paste the contents of `backend/supabase_schema.sql` into the editor.
    *   Click **Run** to create the `users` table.
3.  **Create Storage Bucket**:
    *   Go to **Storage** in the left menu.
    *   Click **New bucket**.
    *   Name it **`screenshots`**.
    *   Toggle **Public bucket** to **ON** (this is required so Telegram can fetch the screenshot URL to display to the admin).
    *   Click **Save**.

---

## Step 2: Prepare the MikroTik Router

Because Vercel runs in the cloud, it needs to reach your router API over the public internet.

1.  **Enable API Service**:
    *   Open WinBox or SSH into your MikroTik router.
    *   Verify the API service is enabled:
        ```routeros
        /ip service enable api
        /ip service set api port=8728
        ```
2.  **Expose the API Port**:
    *   Set up **Port Forwarding (NAT)** on your router or ISP gateway so that incoming traffic to your public WAN IP (or Dynamic DNS domain) on port `8728` is forwarded to your router's local IP address.
    *   Ensure your password for the MikroTik API user is strong.
3.  **Configure Hotspot Profiles**:
    *   In WinBox, navigate to **IP** -> **Hotspot** -> **User Profiles**.
    *   Add profiles matching the names used by the backend:
        *   **`15-days-40TK`**
        *   **`30-days-100TK`**
    *   Configure speed limits (rate limits) and session constraints on these profiles as desired.

---

## Step 3: Deploy to Vercel

1.  **Push Code to GitHub**:
    *   Initialize a git repository in the project folder, commit all files, and push it to a private GitHub repository.
2.  **Import to Vercel**:
    *   Sign up/login to [vercel.com](https://vercel.com/).
    *   Click **Add New...** -> **Project**.
    *   Import your GitHub repository.
3.  **Configure Environment Variables**:
    *   Under the **Environment Variables** section, add the following variables:
        *   `SUPABASE_URL`: Find this in Supabase under **Project Settings** -> **API** -> **Project URL**.
        *   `SUPABASE_KEY`: Use the **`service_role` (secret)** key (NOT the `anon`/`public` key). This is required to bypass Row Level Security (RLS) for server queries.
        *   `MIKROTIK_IP`: Your public WAN IP address or Dynamic DNS hostname (e.g. `myrouter.ddns.net`).
        *   `MIKROTIK_USER`: MikroTik API username (e.g. `admin`).
        *   `MIKROTIK_PASS`: MikroTik API password.
        *   `MIKROTIK_API_PORT`: `8728` (default).
        *   `TELEGRAM_BOT_TOKEN`: The bot token obtained from `@BotFather`.
        *   `TELEGRAM_CHAT_ID`: Your admin Telegram chat ID.
4.  **Deploy**:
    *   Click **Deploy**. Once completed, Vercel will provide a public URL (e.g. `https://mikrotik-hotspot.vercel.app`).

---

## Step 4: Register the Telegram Webhook

Once the Vercel site is live, you must register its webhook route with Telegram so the bot receives callback queries:

1.  Open your browser and navigate to:
    ```
    https://YOUR_VERCEL_DOMAIN.vercel.app/api/setup
    ```
    *(Replace `YOUR_VERCEL_DOMAIN` with your actual Vercel project domain)*.
2.  You should see a success message: `Webhook successfully configured to .../api/webhook`.
3.  Verify the webhook is working by sending `/start` to your Telegram bot. It should reply with:
    `Welcome, admin! I'm ready to manage hotspot users via webhooks.`

---

## Step 5: Configure Hotspot Pages on MikroTik

1.  Open `login.html` from the root directory.
2.  Locate the registration button/link and update it to point to your new registration URL on Vercel:
    ```html
    <a href="https://YOUR_VERCEL_DOMAIN.vercel.app/register" class="btn">Buy Package</a>
    ```
3.  Upload the updated HTML files (`login.html`, `logout.html`, `status.html`, etc.) and `md5.js` to the `/hotspot` folder on your MikroTik router (typically using FTP or WinBox Files).
4.  Add a walled-garden entry so unauthenticated hotspot users can access Vercel and Supabase assets:
    ```routeros
    /ip hotspot walled-garden add dst-host=YOUR_VERCEL_DOMAIN.vercel.app action=accept
    /ip hotspot walled-garden add dst-host=*.supabase.co action=accept
    ```
