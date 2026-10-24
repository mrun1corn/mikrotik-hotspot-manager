import io
import time
import secrets
import string
import datetime
try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False
import requests
from flask import Blueprint, request, render_template, send_file, url_for
from PIL import Image, ImageDraw, ImageFont
from telebot import types

try:
    from backend.config import (
        TELEGRAM_CHAT_ID, CRON_SECRET, SUPABASE_URL, SUPABASE_KEY, logger
    )
    from backend.database import db
    from backend.mikrotik import mikrotik
    from backend.bot import bot, notify_admin_error
    from backend.security import (
        sanitize_username, generate_download_token,
        verify_download_token, verify_image_file, check_rate_limit
    )
except ImportError:
    from config import (
        TELEGRAM_CHAT_ID, CRON_SECRET, SUPABASE_URL, SUPABASE_KEY, logger
    )
    from database import db
    from mikrotik import mikrotik
    from bot import bot, notify_admin_error
    from security import (
        sanitize_username, generate_download_token,
        verify_download_token, verify_image_file, check_rate_limit
    )

web_bp = Blueprint('web', __name__)

@web_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
        if not check_rate_limit(client_ip, limit=5, window=300):
            return render_template(
                'register.html',
                message="Too many registration attempts. Please wait a few minutes.",
                message_type="error"
            ), 429

        raw_phone = request.form.get('phone', '').strip()
        package = request.form.get('package', '').strip()
        trx_id = request.form.get('trx_id', '').strip()
        screenshot = request.files.get('screenshot')

        import re
        digits = re.sub(r'[^0-9]', '', raw_phone)
        if digits.startswith('880') and len(digits) == 13:
            phone = digits[2:]
        elif len(digits) == 10 and digits.startswith('1'):
            phone = '0' + digits
        else:
            phone = digits

        if not phone or len(phone) != 11 or not phone.startswith('01'):
            return render_template('register.html', message="Please enter a valid 11-digit phone number.", message_type="error")

        if package not in ("15_days_40_tk", "30_days_100_tk"):
            return render_template('register.html', message="Invalid package selected.", message_type="error")

        screenshot_url = f"trx:{trx_id}" if trx_id else "manual_submission"
        if screenshot and screenshot.filename:
            screenshot_bytes = screenshot.read()
            is_valid_img, img_err = verify_image_file(screenshot_bytes)
            if not is_valid_img:
                return render_template('register.html', message=img_err, message_type="error")

            screenshot_filename = f"{phone}_{int(time.time())}_{sanitize_username(screenshot.filename or 'screenshot.png')}"
            try:
                uploaded = db.upload_screenshot(
                    filename=screenshot_filename,
                    file_bytes=screenshot_bytes,
                    content_type=screenshot.content_type
                )
                if uploaded:
                    screenshot_url = uploaded
            except Exception as e:
                logger.error(f"Screenshot upload failed: {e}")
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        user_data = {
            "username": username,
            "phone": phone,
            "package": package,
            "password": password,
            "screenshot_url": screenshot_url,
            "registration_timestamp": now_str,
            "approved": False,
            "approval_timestamp": None,
            "expiration_timestamp": None,
            "telegram_message_id": None
        }

        try:
            db.insert_user(user_data)
        except Exception as e:
            logger.error(f"DB insert failed for user '{username}': {e}")
            db.delete_screenshot(screenshot_url)
            return render_template('register.html', message="Database error.", message_type="error")

        # Pre-create user on router in disabled state
        mikrotik.add_hotspot_user(username, password, package)

        # Telegram notification with interactive Approve / Reject buttons
        caption = (
            f"📋 **New Registration Request!**\n\n"
            f"👤 **User:** `{username}`\n"
            f"📞 **Phone:** `{phone}`\n"
            f"📦 **Package:** `{package.replace('_', ' ').title()}`\n"
            f"🆔 **Payment:** `{trx_id or 'Direct Submission'}`\n"
            f"🔑 **Password:** `{password}`\n\n"
            f"Tap Approve below to activate:"
        )
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton("✅ Approve & Activate", callback_data=f"approve_{username}"),
            types.InlineKeyboardButton("❌ Reject & Delete", callback_data=f"reject_{username}")
        )

        try:
            if screenshot_url.startswith("http"):
                message = bot.send_photo(TELEGRAM_CHAT_ID, screenshot_url, caption=caption, reply_markup=keyboard)
            else:
                message = bot.send_message(TELEGRAM_CHAT_ID, caption, parse_mode="Markdown", reply_markup=keyboard)
            db.update_user(username, {"telegram_message_id": message.message_id})
        except Exception as e:
            logger.error(f"Telegram notification failed for '{username}': {e}")
            notify_admin_error("register/telegram", f"Registration saved but notification failed for {username}: {e}")

        # Secure download link with HMAC signature token
        download_token = generate_download_token(username, password)
        download_link = url_for('web.download_credentials', username=username, token=download_token)

        return render_template(
            'success.html',
            username=username,
            password=password,
            download_link=download_link,
            auto_approved=False,
            trx_id=trx_id or 'Verification Pending'
        )

    return render_template('register.html')

@web_bp.route('/download/<username>')
def download_credentials(username):
    username = sanitize_username(username)
    token = request.args.get('token', '')

    if not username:
        return "Invalid username", 400
    if not token:
        return "Access denied: Missing download token.", 403

    try:
        user_data = db.get_user_by_username(username)
    except Exception as e:
        logger.error(f"DB lookup failed for download '{username}': {e}")
        return "Service unavailable", 503

    if not user_data:
        return "User not found", 404

    # Cryptographic validation of access token
    if not verify_download_token(username, user_data['password'], token):
        logger.warning(f"Unauthorized credential download attempt for '{username}'")
        return "Access denied: Missing or invalid download token.", 403

    username_text = f"Username: {username}"
    # QR Code (if qrcode library available)
    if HAS_QRCODE:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=4,
            border=2,
        )
        qr.add_data(f"USER:{username};PASS:{user_data['password']}")
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        img.paste(qr_img, (400, 20))
    d.text((20, 160), "Status: Pending Admin Approval", fill=(102, 102, 102), font=font)
    d.text((20, 200), "Connect to Wi-Fi and login once approved.", fill=(153, 153, 153), font=font)

    # QR Code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=4,
        border=2,
    )
    qr.add_data(f"USER:{username};PASS:{user_data['password']}")
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    img.paste(qr_img, (400, 20))

    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)

    return send_file(img_io, mimetype='image/png', as_attachment=True, download_name=f"{username}_credentials.png")

@web_bp.route('/')
@web_bp.route('/status')
def status_dashboard():
    # Public visit to root / renders register page
    if request.path == '/' and not request.args.get('key'):
        return render_template('register.html')

    # Status dashboard requires key or bearer auth if CRON_SECRET is configured
    key = request.args.get('key', '')
    auth = request.headers.get('Authorization', '')
    if CRON_SECRET and not (key == CRON_SECRET or auth == f'Bearer {CRON_SECRET}'):
        return render_template('register.html')

    # 1. MikroTik status
    mt_status = "Not Connected"
    mt_uptime = "Unknown"
    pool = mikrotik.connect()
    if pool:
        try:
            api = pool.get_api()
            res = api.get_resource('/system/resource').get()
            if res:
                mt_uptime = res[0].get('uptime', 'Unknown')
                mt_status = "Connected ✅"
        except Exception as e:
            mt_status = f"Error: {e}"
        finally:
            pool.disconnect()
    else:
        mt_status = "Failed to connect ❌"

    # 2. Telegram status
    tg_bot = "Unknown"
    tg_webhook = "Unknown"
    try:
        me = bot.get_me()
        tg_bot = f"@{me.username} ✅"
        wh = bot.get_webhook_info()
        if wh.url:
            tg_webhook = f"Active ({wh.url}) ✅"
            if wh.pending_update_count > 0:
                tg_webhook += f" [Pending updates: {wh.pending_update_count}]"
            if wh.last_error_message:
                tg_webhook += f" | Last Error: {wh.last_error_message}"
        else:
            tg_webhook = "Not Set ❌"
    except Exception as e:
        tg_bot = f"Error: {e} ❌"

    # 3. Supabase status
    db_status = "Unknown"
    try:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        res = requests.get(f"{SUPABASE_URL}/rest/v1/users?select=username&limit=1", headers=headers, timeout=5)
        res.raise_for_status()
        db_status = "Connected ✅"
    except Exception as e:
        db_status = f"Error: {e} ❌"

    masked_chat = f"***{str(TELEGRAM_CHAT_ID)[-4:]}" if TELEGRAM_CHAT_ID else "Not Set"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>System Status Dashboard</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; background: #f4f4f9; }}
            .card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); max-width: 600px; margin: 0 auto; }}
            h1 {{ color: #333; }}
            .status-item {{ margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid #eee; }}
            .label {{ font-weight: bold; color: #555; }}
            .value {{ margin-top: 5px; color: #111; word-wrap: break-word; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>📊 System Status Dashboard</h1>
            <div class="status-item">
                <div class="label">🌐 Host:</div>
                <div class="value">{request.host}</div>
            </div>
            <div class="status-item">
                <div class="label">🤖 Telegram Bot:</div>
                <div class="value">{tg_bot}</div>
            </div>
            <div class="status-item">
                <div class="label">🔗 Telegram Webhook:</div>
                <div class="value">{tg_webhook}</div>
            </div>
            <div class="status-item">
                <div class="label">📡 MikroTik Router:</div>
                <div class="value">{mt_status} (Uptime: {mt_uptime})</div>
            </div>
            <div class="status-item">
                <div class="label">🗄️ Supabase Database:</div>
                <div class="value">{db_status}</div>
            </div>
            <div class="status-item">
                <div class="label">Admin Chat ID Configured:</div>
                <div class="value">{masked_chat}</div>
            </div>
        </div>
    </body>
    </html>
    """
    return html

@web_bp.route('/api/user/status/<username>', methods=['GET'])
def user_approval_status(username):
    username = sanitize_username(username)
    if not username:
        return {"approved": False, "status": "INVALID"}, 400
    user = db.get_user_by_username(username)
    if not user:
        return {"approved": False, "status": "NOT_FOUND"}, 404
    return {
        "username": username,
        "approved": bool(user.get("approved")),
        "status": "APPROVED" if user.get("approved") else "PENDING"
    }, 200
