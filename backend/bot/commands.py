import secrets
import string
import datetime
import requests
from telebot import types

from backend.config.settings import (
    TELEGRAM_CHAT_ID, SUPABASE_URL, SUPABASE_KEY, logger
)
from backend.bot.instance import bot
from backend.bot.keyboards import get_admin_keyboard, get_reboot_keyboard
from backend.mikrotik import mikrotik
from backend.database import db
from backend.security import sanitize_username

def register_command_handlers():
    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        if message.chat.id == TELEGRAM_CHAT_ID:
            bot.reply_to(message, "Welcome, admin! Use the menu below to easily manage your hotspot.", reply_markup=get_admin_keyboard())
        else:
            bot.reply_to(message, "You are not authorized to use this bot.")

    @bot.message_handler(commands=['help'])
    def send_help(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        text = (
            "🛠 **Available Commands:**\n\n"
            "/start - Check bot authorization\n"
            "/status - View system & router status\n"
            "/logs - View recent sensitive security & login logs\n"
            "/active - View currently connected users\n"
            "/users - List all active/approved users\n"
            "/pending - List users awaiting approval\n"
            "/packages - Edit package speeds with interactive buttons\n"
            "/add `<phone>` `<package>` - Instantly create and approve a user\n"
            "/sync - Initialize a fresh router with packages & walled garden\n"
            "/kick `<username>` - Disconnect an active user session\n"
            "/delete `<username>` - Completely remove a user\n"
            "/reboot - Restart the MikroTik router\n"
            "/help - Show this message"
        )
        bot.reply_to(message, text, parse_mode="Markdown")

    @bot.message_handler(commands=['status'])
    def bot_status_check(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        msg = bot.reply_to(message, "⏳ Checking system status...")
        mt_status = "❌ Disconnected"
        res = mikrotik.system.get_resource()
        if res:
            uptime = res.get('uptime', 'Unknown')
            mt_status = f"✅ Connected (Uptime: {uptime})"

        db_status = "❌ Disconnected"
        try:
            headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
            res = requests.get(f"{SUPABASE_URL}/rest/v1/users?select=username", headers=headers, timeout=5)
            if res.status_code == 200:
                count = len(res.json())
                db_status = f"✅ Connected ({count} total users)"
        except Exception:
            pass

        text = f"📊 **System Status**\n\n📡 **MikroTik:** {mt_status}\n🗄 **Database:** {db_status}"
        bot.edit_message_text(text, chat_id=message.chat.id, message_id=msg.message_id, parse_mode="Markdown")

    @bot.message_handler(commands=['logs'])
    def security_logs_cmd(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        msg = bot.reply_to(message, "🔍 Fetching sensitive security logs from MikroTik...")
        try:
            all_logs = mikrotik.get_logs()
            security_events = []
            for l in all_logs:
                m = l.get('message', '')
                if any(term in m.lower() for term in ['login failure', 'logged in', 'logged out', 'auto-ban', 'blocked', 'reboot', 'changed by', 'critical', 'warning']):
                    security_events.append(l)

            if not security_events:
                bot.edit_message_text("✅ No critical security events found in router log buffer.", chat_id=message.chat.id, message_id=msg.message_id)
                return

            recent = security_events[-10:]
            text = "🚨 **Recent Sensitive Security Logs:**\n\n"
            for r in recent:
                t = r.get('time', '')
                m = r.get('message', '')
                icon = "🔴" if "failure" in m.lower() or "blocked" in m.lower() or "auto-ban" in m.lower() else "🟢"
                text += f"{icon} `[{t}]` {m}\n\n"

            bot.edit_message_text(text, chat_id=message.chat.id, message_id=msg.message_id, parse_mode="Markdown")
        except Exception as e:
            bot.edit_message_text(f"⚠️ Error reading logs: {e}", chat_id=message.chat.id, message_id=msg.message_id)

    @bot.message_handler(commands=['users'])
    def list_users(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        try:
            users = db.get_all_users(approved=True)
            if not users:
                bot.reply_to(message, "No active users found.")
                return
            text = "👥 **Active Users:**\n"
            for u in users:
                exp = u.get('expiration_timestamp')
                exp_str = exp.split('T')[0] if exp else "Unknown"
                text += f"• `{u['username']}` | Exp: {exp_str}\n"
            bot.reply_to(message, text, parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"Database error: {e}")

    @bot.message_handler(commands=['pending'])
    def list_pending(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        try:
            users = db.get_all_users(approved=False)
            if not users:
                bot.reply_to(message, "No pending registrations.")
                return
            text = "⏳ **Pending Approvals:**\n"
            for u in users:
                reg = u.get('registration_timestamp', '').split('T')[0]
                text += f"• `{u['username']}` ({u.get('package', 'N/A')}) - {reg}\n"
            bot.reply_to(message, text, parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"Database error: {e}")

    @bot.message_handler(commands=['delete'])
    def delete_user_cmd(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "Usage: `/delete <username>`", parse_mode="Markdown")
            return
        username = sanitize_username(args[1])
        try:
            user = db.get_user_by_username(username)
            if not user:
                bot.reply_to(message, f"User `{username}` not found in database.", parse_mode="Markdown")
                return
            db.delete_user(username)
            mt_deleted = mikrotik.delete_hotspot_user(username)
            mt_status = "✅ Removed from MikroTik" if mt_deleted else "⚠️ Not found/failed in MikroTik"
            bot.reply_to(message, f"🗑 User `{username}` deleted.\n{mt_status}", parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"Error deleting user: {e}")

    @bot.message_handler(commands=['active'])
    def list_active(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        active_users = mikrotik.get_active_users()
        if not active_users:
            bot.reply_to(message, "No active sessions on the router right now.")
            return
        text = "🟢 **Currently Connected Sessions:**\n\n"
        for u in active_users:
            name = u.get('user', 'Unknown')
            addr = u.get('address', 'Unknown')
            uptime = u.get('uptime', '0s')
            text += f"• `{name}` | IP: {addr} | Uptime: {uptime}\n"
        bot.reply_to(message, text, parse_mode="Markdown")

    @bot.message_handler(commands=['kick'])
    def kick_user_cmd(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "Usage: `/kick <username>`", parse_mode="Markdown")
            return
        username = sanitize_username(args[1])
        if mikrotik.kick_user(username):
            bot.reply_to(message, f"👢 Kicked active session for `{username}`.", parse_mode="Markdown")
        else:
            bot.reply_to(message, f"⚠️ Could not find active session for `{username}` or error occurred.", parse_mode="Markdown")

    @bot.message_handler(commands=['reboot'])
    def reboot_cmd(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        bot.reply_to(message, "⚠️ **WARNING:** Are you sure you want to REBOOT the MikroTik router?", parse_mode="Markdown", reply_markup=get_reboot_keyboard())

    @bot.message_handler(commands=['add'])
    def add_user_cmd(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        args = message.text.split()
        if len(args) < 3:
            bot.reply_to(message, "Usage: `/add <phone> <package>`\nPackages: `15_days_40_tk` or `30_days_100_tk`", parse_mode="Markdown")
            return
        phone = sanitize_username(args[1])
        package = args[2]
        if package not in ("15_days_40_tk", "30_days_100_tk"):
            bot.reply_to(message, "Invalid package. Use `15_days_40_tk` or `30_days_100_tk`", parse_mode="Markdown")
            return
        username = phone
        password = ''.join(secrets.choice(string.digits) for _ in range(6))
        now = datetime.datetime.now(datetime.timezone.utc)
        expiration_days = 15 if package == "15_days_40_tk" else 30
        expiration_time = now + datetime.timedelta(days=expiration_days)
        user_data = {
            "username": username,
            "phone": phone,
            "package": package,
            "password": password,
            "screenshot_url": "manual_add",
            "registration_timestamp": now.isoformat(),
            "approved": True,
            "approval_timestamp": now.isoformat(),
            "expiration_timestamp": expiration_time.isoformat(),
            "telegram_message_id": 0
        }
        try:
            db.insert_user(user_data)
            if mikrotik.add_hotspot_user(username, password, package) and mikrotik.enable_hotspot_user(username):
                text = (
                    f"✅ **User Manually Created & Approved!**\n\n"
                    f"👤 **Username:** `{username}`\n"
                    f"🔑 **Password:** `{password}`\n"
                    f"📦 **Package:** `{package}`\n"
                    f"⏳ **Expires:** {expiration_time.strftime('%Y-%m-%d')}"
                )
                bot.reply_to(message, text, parse_mode="Markdown")
            else:
                bot.reply_to(message, "⚠️ Added to DB, but failed to create in MikroTik router!")
        except Exception as e:
            bot.reply_to(message, f"Database error: {e}")

    @bot.message_handler(commands=['packages'])
    def packages_cmd(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        msg = bot.reply_to(message, "⏳ Fetching packages from router...")
        profiles = mikrotik.get_profiles()
        if not profiles:
            bot.edit_message_text("⚠️ Failed to fetch packages from MikroTik.", chat_id=message.chat.id, message_id=msg.message_id)
            return
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        text = "📦 **Manage Hotspot Packages**\n\nCurrent Speeds:\n"
        for p in profiles:
            name = p.get('name')
            if name == 'default':
                continue
            limit = p.get('rate-limit', 'Unlimited')
            text += f"• `{name}`: {limit}\n"
            keyboard.add(types.InlineKeyboardButton(f"⚙️ Edit {name}", callback_data=f"pkg_{name}"))
        bot.edit_message_text(text, chat_id=message.chat.id, message_id=msg.message_id, parse_mode="Markdown", reply_markup=keyboard)

    @bot.message_handler(commands=['setlimit'])
    def set_limit_cmd(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        args = message.text.split()
        if len(args) < 3:
            bot.reply_to(message, "Usage: `/setlimit <profile_name> <limit>`\nExample: `/setlimit 15-days-40TK 3M/3M`", parse_mode="Markdown")
            return
        profile = args[1]
        limit = args[2]
        if mikrotik.set_profile_limit(profile, limit):
            bot.reply_to(message, f"✅ Successfully updated profile `{profile}` to `{limit}`.", parse_mode="Markdown")
        else:
            bot.reply_to(message, f"⚠️ Failed to update profile `{profile}`. Does it exist?", parse_mode="Markdown")

    @bot.message_handler(commands=['sync'])
    def sync_cmd(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        bot.reply_to(message, "⚙️ Syncing router configurations...")
        result = mikrotik.sync_initial_setup()
        bot.reply_to(message, f"**Sync Result:**\n{result}", parse_mode="Markdown")

    # --- Interactive Text Button Handlers ---
    @bot.message_handler(func=lambda m: m.text == "📊 System Status")
    def text_status(m): bot_status_check(m)

    @bot.message_handler(func=lambda m: m.text == "🚨 Security Logs")
    def text_logs(m): security_logs_cmd(m)

    @bot.message_handler(func=lambda m: m.text == "📦 Manage Packages")
    def text_packages(m): packages_cmd(m)

    @bot.message_handler(func=lambda m: m.text == "👥 Active Users")
    def text_active(m): list_active(m)

    @bot.message_handler(func=lambda m: m.text == "⏳ Pending Approvals")
    def text_pending(m): list_pending(m)

    @bot.message_handler(func=lambda m: m.text == "⚙️ Router Sync")
    def text_sync(m): sync_cmd(m)

    @bot.message_handler(func=lambda m: m.text == "🔄 Reboot Router")
    def text_reboot(m): reboot_cmd(m)

    @bot.message_handler(func=lambda m: m.text == "ℹ️ Help")
    def text_help(m): send_help(m)
