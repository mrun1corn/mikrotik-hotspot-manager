import datetime
from flask import Blueprint, jsonify
from telebot import types

try:
    from backend.config import TELEGRAM_CHAT_ID, logger
    from backend.database import db
    from backend.mikrotik import mikrotik
    from backend.bot import bot
    from backend.security import require_cron_auth, parse_isoformat
except ImportError:
    from config import TELEGRAM_CHAT_ID, logger
    from database import db
    from mikrotik import mikrotik
    from bot import bot
    from security import require_cron_auth, parse_isoformat

cron_bp = Blueprint('cron', __name__)

# Track last sent log entry ID to prevent duplicate alerts
_last_security_log_id = None

@cron_bp.route('/api/cron/check-expiration', methods=['GET', 'POST'])
@require_cron_auth
def cron_check_expiration():
    logger.info("Running expiration checker...")
    errors = []

    try:
        users = db.get_all_users()
    except Exception as e:
        logger.error(f"Cron: DB fetch failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

    users_to_delete = []

    for user_data in users:
        username = user_data["username"]
        try:
            if user_data.get("approved") and user_data.get("expiration_timestamp"):
                expiration_time = parse_isoformat(user_data["expiration_timestamp"])
                if expiration_time and datetime.datetime.now(datetime.timezone.utc) > expiration_time:
                    logger.info(f"User {username} has expired.")
                    if mikrotik.delete_hotspot_user(username):
                        users_to_delete.append(username)
                        if TELEGRAM_CHAT_ID:
                            bot.send_message(TELEGRAM_CHAT_ID, f"⌛ User `{username}` has expired and been removed from MikroTik.", parse_mode="Markdown")
                    else:
                        errors.append(f"MikroTik delete failed for {username}")
                        logger.error(f"Failed to delete expired user {username} from MikroTik.")

            elif not user_data.get("approved"):
                registration_time = parse_isoformat(user_data.get("registration_timestamp"))
                if registration_time and datetime.datetime.now(datetime.timezone.utc) - registration_time > datetime.timedelta(hours=24):
                    logger.info(f"Unapproved user {username} older than 24h, removing.")
                    users_to_delete.append(username)
                    if TELEGRAM_CHAT_ID:
                        bot.send_message(TELEGRAM_CHAT_ID, f"🗑 Unapproved user `{username}` removed after 24 hours.", parse_mode="Markdown")
        except Exception as e:
            errors.append(f"{username}: {e}")
            logger.error(f"Cron error processing user {username}: {e}", exc_info=True)
            continue

    for username in users_to_delete:
        try:
            db.delete_user(username)
        except Exception as e:
            errors.append(f"Cleanup {username}: {e}")
            logger.error(f"Cron cleanup error for {username}: {e}")

    # Also run security log monitor pass
    check_and_notify_security_logs()

    status = "ok" if not errors else "partial"
    return jsonify({"status": status, "deleted": len(users_to_delete), "errors": errors}), 200

def check_and_notify_security_logs():
    """Fetches new sensitive router logs and forwards them to Telegram."""
    global _last_security_log_id
    if not TELEGRAM_CHAT_ID:
        return

    pool = mikrotik.connect()
    if not pool:
        return

    try:
        api = pool.get_api()
        logs_resource = api.get_resource('/log')
        # Fetch recent logs
        logs = logs_resource.get()
        if not logs:
            return

        sensitive_logs = []
        for l in logs:
            msg = l.get('message', '')
            topics = l.get('topics', '')
            # Filter for sensitive security and account events
            if any(term in msg.lower() for term in ['login failure', 'logged in', 'auto-ban', 'reboot', 'changed by', 'breach', 'blocked']):
                sensitive_logs.append(l)

        if not sensitive_logs:
            return

        # On initial pass, record last ID without spamming historical logs
        if _last_security_log_id is None:
            _last_security_log_id = sensitive_logs[-1].get('id')
            return

        # Find new entries after _last_security_log_id
        new_alerts = []
        found_last = False
        for l in sensitive_logs:
            if found_last:
                new_alerts.append(l)
            elif l.get('id') == _last_security_log_id:
                found_last = True

        if not found_last:
            # Buffer rolled over, take last 3
            new_alerts = sensitive_logs[-3:]

        for alert in new_alerts:
            _last_security_log_id = alert.get('id')
            msg = alert.get('message', '')
            time_str = alert.get('time', '')
            icon = "🚨" if "failure" in msg.lower() or "blocked" in msg.lower() or "auto-ban" in msg.lower() else "🛡"
            text = f"{icon} **Security Log Alert**\n\n🕒 `{time_str}`\n📝 `{msg}`"
            bot.send_message(TELEGRAM_CHAT_ID, text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Failed to check security logs: {e}")
    finally:
        pool.disconnect()
