import hmac
import datetime
from flask import Blueprint, request, jsonify
from telebot import types

try:
    from backend.config import (
        TELEGRAM_WEBHOOK_SECRET, CRON_SECRET, APP_URL, TELEGRAM_CHAT_ID, logger
    )
    from backend.bot import bot
    from backend.security import require_admin_auth
except ImportError:
    from config import (
        TELEGRAM_WEBHOOK_SECRET, CRON_SECRET, APP_URL, TELEGRAM_CHAT_ID, logger
    )
    from bot import bot
    from security import require_admin_auth

webhook_bp = Blueprint('webhook', __name__)

@webhook_bp.route('/api/webhook', methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') != 'application/json':
        return 'Forbidden', 403

    # Validate secret token if configured
    expected_secret = TELEGRAM_WEBHOOK_SECRET or CRON_SECRET
    if expected_secret:
        token = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if not hmac.compare_digest(token, expected_secret):
            logger.warning(f"Unauthorized webhook invocation attempt from {request.remote_addr}")
            return 'Unauthorized', 401

    try:
        json_string = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_string)
        bot.process_new_updates([update])
    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)

    # Always return 200 to acknowledge receipt to Telegram
    return '', 200

@webhook_bp.route('/api/setup', methods=['GET'])
@require_admin_auth
def setup_webhook():
    """Sets up Telegram webhook with secret token verification. Protected by admin key."""
    base_url = APP_URL or f"https://{request.host}"
    webhook_url = f"{base_url.rstrip('/')}/api/webhook"
    secret_token = TELEGRAM_WEBHOOK_SECRET or CRON_SECRET or None

    try:
        success = bot.set_webhook(url=webhook_url, secret_token=secret_token)
        if success:
            return f"Webhook successfully configured to {webhook_url} (Secret Token: {'Configured' if secret_token else 'None'})", 200
        else:
            return "Failed to set webhook with Telegram.", 500
    except Exception as e:
        logger.error(f"Webhook setup failed: {e}")
        return f"Webhook setup error: {e}", 500

@webhook_bp.route('/api/notify/login', methods=['GET', 'POST'])
def notify_hotspot_login():
    """Triggered by MikroTik router on-login script when a user connects to Wi-Fi."""
    user = request.args.get('user') or request.form.get('user', 'Unknown')
    ip = request.args.get('ip') or request.form.get('ip', 'Unknown')
    mac = request.args.get('mac') or request.form.get('mac', 'Unknown')

    logger.info(f"Hotspot user connected: user={user}, ip={ip}, mac={mac}")

    if TELEGRAM_CHAT_ID:
        text = (
            f"📶 **Hotspot User Connected!**\n\n"
            f"👤 **User:** `{user}`\n"
            f"🌐 **IP Address:** `{ip}`\n"
            f"📱 **Device MAC:** `{mac}`\n"
            f"🕒 **Time:** `{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}`\n\n"
            f"🟢 Active internet session started."
        )
        try:
            bot.send_message(TELEGRAM_CHAT_ID, text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to send Telegram login notification: {e}")

    return jsonify({"status": True, "message": "Login notification sent"}), 200
