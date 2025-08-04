# MikroTik Hotspot User Management System

This project provides a comprehensive backend system for managing MikroTik Hotspot users, combining a Flask web server for user registration and a Telegram bot for admin approvals and automated user expiration handling.

## Features

*   **Web-based User Registration:** Users can register for hotspot packages via a web form, including phone number, package selection, and payment screenshot upload.
*   **Automated Credential Generation:** Generates unique username (based on phone number) and a 6-digit numeric password.
*   **Payment Approval Workflow:** Admins receive Telegram notifications with payment screenshots and inline "Approve" or "Reject" buttons.
*   **MikroTik Integration:**
    *   Dynamically creates MikroTik Hotspot User Profiles (e.g., "15-days-40TK", "30-days-100TK") on startup.
    *   Adds and enables users in MikroTik upon admin approval.
    *   Deletes expired users from MikroTik automatically.
*   **User Data Persistence:** Stores user information, approval status, and expiration timestamps in `users.json`.
*   **Credentials Download:** Provides a link for users to download an image of their generated username and password.
*   **Automated Expiration Handling:** A periodic job checks for expired users and removes them from MikroTik and the system.

## File Structure

This project is divided into two main parts based on their deployment location:

### 1. Python Server Files (Run on your dedicated server/PC)

```
dir
├───backend/
│   ├───main.py             # Main application logic (Flask, Telegram bot, MikroTik integration)
│   ├───requirements.txt    # Python dependencies
│   ├───.env                # Environment variables for configuration
│   ├───users.json          # Stores registered user data
│   ├───templates/
│   │   ├───register.html   # Web registration form
│   │   └───success.html    # Page displayed after successful registration
│   ├───uploads/            # Directory to store payment screenshots
│   └───credentials/        # Directory to store generated credentials images

```

### 2. MikroTik Hotspot Files (Upload to MikroTik Router's `/hotspot` directory)

```
/hotspot/
├───login.html              # Modified hotspot login page
├───... (other default MikroTik hotspot files like alogin.html, error.html, etc.)
```

## Deployment Architecture

This system operates with two distinct deployment locations:

1.  **Python Server:** Your `backend/` directory (containing `main.py`, `requirements.txt`, `.env`, `users.json`, `templates/`, `uploads/`, `credentials/`) should be deployed and run on a dedicated server or PC with a static IP address (e.g., `172.16.0.6` or `192.168.5.245`). This machine hosts the Flask web server and runs the Telegram bot.

2.  **MikroTik Router:** The `login.html` file (and any other custom hotspot pages like `alogin.html`, `error.html` if modified) needs to be uploaded to your MikroTik router's hotspot directory (typically `/flash/hotspot` or `/hotspot`). This allows the MikroTik to serve the custom login page to hotspot users.

    **Important:** Ensure the `login.html` file uploaded to MikroTik contains the correct link to your Flask server's `/register` page (e.g., `http://YOUR_FLASK_SERVER_IP:5000/register`).

## Prerequisites

Before you begin, ensure you have the following:

*   **Python 3.x** installed on your server machine.
*   **pip** (Python package installer).
*   **MikroTik Router** with Hotspot configured and API service enabled (default port 8728).
*   **Telegram Bot Token:** Create a new bot via BotFather on Telegram and obtain its API token.
*   **Telegram Chat ID:** Get your Telegram chat ID (you can use a bot like `@userinfobot` to find it).
*   **Server IP Address:** The static IP address of the machine hosting this application (e.g., `172.16.0.6` or `192.168.5.245`).

## Setup Instructions

1.  **Navigate to the Project Directory:**
    Open your terminal or command prompt and go to the `backend` directory:
    ```bash
    cd C:\Users\Joy Cinemas\Documents\mbk\backend
    ```

2.  **Install Python Dependencies:**
    Install all required Python libraries using pip:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure Environment Variables:**
    Open the `.env` file located in the `backend` directory (`C:\Users\Joy Cinemas\Documents\mbk\backend\.env`) and fill in the details:
    ```
    MIKROTIK_IP=YOUR_MIKROTIK_ROUTER_IP  # e.g., 192.168.5.235
    MIKROTIK_USER=YOUR_MIKROTIK_API_USER # e.g., admin
    MIKROTIK_PASS=YOUR_MIKROTIK_API_PASSWORD # e.g., robin01716
    MIKROTIK_API_PORT=8728               # Default MikroTik API port
    TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID=YOUR_TELEGRAM_CHAT_ID # Your admin Telegram chat ID
    SERVER_IP=YOUR_FLASK_SERVER_IP       # e.g., 172.16.0.6 or 192.168.5.245
    ```
    **Important:** Ensure `SERVER_IP` matches the actual IP address of the machine running this Flask application.

## MikroTik Router Configuration

You need to configure your MikroTik router to allow the hotspot users to access the registration page and for the Flask application to communicate with the MikroTik API.

1.  **Enable MikroTik API Service:**
    Connect to your MikroTik router (e.g., via WinBox or SSH) and ensure the API service is enabled:
    ```
    /ip service enable api
    /ip service set api port=8728
    ```
    (Verify the port matches `MIKROTIK_API_PORT` in your `.env` file).

2.  **Configure Walled Garden:**
    Add a Walled Garden rule to allow unauthenticated hotspot users to access your Flask registration server. Replace `YOUR_FLASK_SERVER_IP` with the `SERVER_IP` you configured in `.env`:
    ```
    /ip hotspot walled-garden add dst-host=YOUR_FLASK_SERVER_IP action=accept
    ```
    Example: `/ip hotspot walled-garden add dst-host=172.16.0.6 action=accept`

3.  **Upload Hotspot UI Files to MikroTik:**
    The following files in your project's root directory (`C:/Users/Joy Cinemas/Documents/mbk/`) have been updated with a modern, responsive UI, dark/light mode support, and a "Buy Package" button (in `login.html`):
    *   `login.html`
    *   `logout.html`
    *   `status.html`
    *   `alogin.html`
    *   `error.html`
    *   `redirect.html`
    *   `rlogin.html`
    *   `radvert.html`

    You need to **upload all these modified HTML files** to your MikroTik router's hotspot directory (usually `/flash/hotspot` or `/hotspot`).

    **For the Logo:** The UI includes a placeholder for a logo (`<img src="/img/your_logo.png" ...>`). You should:
    *   Create your logo image (e.g., `your_logo.png`).
    *   Upload this logo image to the `/img` directory within your MikroTik router's hotspot folder (you might need to create this `/img` directory if it doesn't exist).

4.  **MikroTik Hotspot User Profiles:**
    The `main.py` script will automatically create the necessary hotspot user profiles (`15-days-40TK`, `30-days-100TK`) on your MikroTik router when it starts, if they don't already exist.

## Running the Application

From the `backend` directory (`C:\Users\Joy Cinemas\Documents\mbk\backend`), run the `main.py` script using your Python 3.13 executable:

```bash
C:\Python313\python.exe main.py
```
(Note: If `python` or `python3` works directly for you, you can use that instead, but `C:\Python313\python.exe` is the most reliable way given previous troubleshooting.)

The Flask web server and the Telegram bot will start concurrently. You should see output indicating the Flask app is running and the MikroTik connection is established.

## Usage

### User Registration (Web)

1.  Users connect to your MikroTik Hotspot.
2.  They will be redirected to the hotspot login page.
3.  Click the "Buy Package" button.
4.  Fill out the registration form (phone number, package, payment screenshot).
5.  Upon submission, they will be redirected to a success page showing their generated username and password, with an option to download an image of these credentials.

### Admin Approval/Rejection (Telegram Bot)

1.  When a new user registers, your Telegram bot will send a message to the `TELEGRAM_CHAT_ID` (your admin chat) with the user's details and payment screenshot.
2.  The message will contain inline "Approve" and "Reject" buttons.
3.  **Approve:** Clicking "Approve" will:
    *   Create the user in MikroTik Hotspot with the assigned profile and enable them.
    *   Update `users.json` with approval and expiration timestamps.
    *   Notify you via Telegram that the user has been approved.
4.  **Reject:** Clicking "Reject" will:
    *   Remove the user's record from `users.json`.
    *   Notify you via Telegram that the user has been rejected.

### Automated Expiration Handling

*   The Telegram bot runs a periodic job every 10 minutes.
*   It checks `users.json` for approved users whose expiration timestamp has passed.
*   Expired users are automatically deleted from MikroTik and removed from `users.json`.
*   You will receive a Telegram notification for each expired user removed.
*   Unapproved users older than 24 hours are also automatically removed from `users.json`.

## Troubleshooting

*   **"This site can't be reached" / "Gateway Timeout" on web registration:**
    *   Ensure your Flask server is running (`C:\Python313\python.py main.py` output should show `Flask app running on http://YOUR_SERVER_IP:5000`).
    *   Verify `SERVER_IP` in `.env` matches the actual IP of your server machine.
    *   Check your server machine's firewall (e.g., Windows Defender Firewall) and ensure TCP port `5000` is open for incoming connections. Temporarily disabling it can help diagnose.
    *   Confirm the MikroTik Walled Garden rule is correctly configured for your `SERVER_IP`.
    *   Ping your `SERVER_IP` from the MikroTik terminal (`/ping YOUR_FLASK_SERVER_IP`).

*   **"Error adding MikroTik user..." / "'RouterOsApi' object has no attribute 'path'":**
    *   Ensure your MikroTik API service is enabled and accessible on the configured port.
    *   Verify `MIKROTIK_IP`, `MIKROTIK_USER`, `MIKROTIK_PASS`, `MIKROTIK_API_PORT` in your `.env` are correct.
    *   Check MikroTik firewall rules that might block API access from your Flask server's IP.

*   **Telegram bot not responding:**
    *   Ensure `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` are correct.
    *   Make sure the bot is running (part of `main.py`).
    *   Send a `/start` command to your bot in Telegram to initiate interaction.

## Future Improvements (Ideas)

*   **bKash Transaction ID/OCR:** Integrate bKash payment gateway or OCR for automated payment verification.
*   **CAPTCHA and Rate Limiting:** Implement security measures on the registration form.
*   **Detailed Logging:** Enhance logging for better debugging and auditing.
*   **User Notification Page:** A page where users can check their package status.
*   **Data Backup/Database:** Implement regular backups for `users.json` or migrate to a more robust database (e.g., SQLite).
*   **MikroTik API Error Handling:** More sophisticated retry mechanisms for API calls.

*   **HTTPS:** Serve Flask over HTTPS for enhanced security.
*   **Mobile-Friendly UI:** Improve the web interface for better mobile experience.
