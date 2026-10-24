import secrets
import string
import datetime
import requests
from telebot import types

from backend.config.settings import (
    TELEGRAM_CHAT_ID, SUPABASE_URL, SUPABASE_KEY, logger
)
from backend.bot.instance import bot
from backend.bot.keyboards import get_admin_keyboard, get_reboot_keyboard, get_user_actions_keyboard
from backend.mikrotik import mikrotik
from backend.database import db
from backend.security import sanitize_username, parse_isoformat

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
            "🛠 **Admin Command Center:**\n\n"
            "📊 **Monitoring & Reports:**\n"
            "/status - Router & database health\n"
            "/sales - Today, monthly & total revenue\n"
            "/traffic - Real-time WAN download/upload speed\n"
            "/active - Live connected user sessions\n"
            "/logs - Sensitive router & security audit logs\n\n"
            "👥 **User & Voucher Management:**\n"
            "/find `<phone/user>` - Lookup user details, expiry & live status\n"
            "/extend `<user>` `<days>` - Add days to user expiration\n"
            "/add `<phone>` `<package>` - Create & approve user instantly\n"
            "/users - List all active users & expiries\n"
            "/pending - List users awaiting approval\n"
            "/kick `<user>` - Disconnect live session\n"
            "/delete `<user>` - Permanently delete user\n\n"
            "🛡️ **Security & System Control:**\n"
            "/blocked - View currently blacklisted IPs\n"
            "/unblock `<ip>` - Remove IP from firewall blacklist\n"
            "/packages - View & edit profile speed limits\n"
            "/sync - Re-sync router packages & walled-garden\n"
            "/reboot - Reboot the MikroTik router\n"
            "/help - Show this guide"
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

    @bot.message_handler(commands=['sales', 'revenue'])
    def sales_report_cmd(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        msg = bot.reply_to(message, "⏳ Calculating sales & revenue report...")
        try:
            users = db.get_all_users()
            today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
            month_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")

            today_rev = 0
            today_count = 0
            month_rev = 0
            month_count = 0
            total_rev = 0
            total_approved = 0
            pkg_counts = {"15_days_40_tk": 0, "30_days_100_tk": 0}

            for u in users:
                if u.get('approved'):
                    total_approved += 1
                    pkg = u.get('package', '')
                    price = 40 if pkg == "15_days_40_tk" else 100
                    total_rev += price
                    if pkg in pkg_counts:
                        pkg_counts[pkg] += 1

                    app_time = u.get('approval_timestamp', '') or ''
                    if app_time.startswith(today_str):
                        today_rev += price
                        today_count += 1
                    if app_time.startswith(month_str):
                        month_rev += price
                        month_count += 1

            text = (
                f"💰 **Hotspot Sales & Revenue Report**\n\n"
                f"📅 **Today ({today_str}):**\n"
                f"• Revenue: **{today_rev} BDT** ({today_count} purchases)\n\n"
                f"🗓️ **This Month ({month_str}):**\n"
                f"• Revenue: **{month_rev} BDT** ({month_count} purchases)\n\n"
                f"💎 **All-Time Total:**\n"
                f"• Total Revenue: **{total_rev} BDT**\n"
                f"• Active Customers: **{total_approved}**\n\n"
                f"📦 **Packages Breakdown:**\n"
                f"• 15 Days (40 TK): `{pkg_counts['15_days_40_tk']}` sold\n"
                f"• 30 Days (100 TK): `{pkg_counts['30_days_100_tk']}` sold"
            )
            bot.edit_message_text(text, chat_id=message.chat.id, message_id=msg.message_id, parse_mode="Markdown")
        except Exception as e:
            bot.edit_message_text(f"⚠️ Error generating sales report: {e}", chat_id=message.chat.id, message_id=msg.message_id)

    @bot.message_handler(commands=['traffic', 'speed', 'bandwidth'])
    def traffic_monitor_cmd(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        msg = bot.reply_to(message, "⏳ Reading live interface traffic...")
        pool = mikrotik.connect()
        if not pool:
            bot.edit_message_text("⚠️ Could not connect to MikroTik router.", chat_id=message.chat.id, message_id=msg.message_id)
            return
        try:
            api = pool.get_api()
            res = api.get_resource('/interface').call('monitor-traffic', {'interface': 'ACL_WAN', 'once': ''})
            if not res:
                bot.edit_message_text("⚠️ Could not read traffic on interface ACL_WAN.", chat_id=message.chat.id, message_id=msg.message_id)
                return
            props = res[0]
            rx_bps = int(props.get('rx-bits-per-second', 0))
            tx_bps = int(props.get('tx-bits-per-second', 0))

            def fmt_speed(bps):
                if bps >= 1000000:
                    return f"{bps / 1000000:.2f} Mbps"
                elif bps >= 1000:
                    return f"{bps / 1000:.1f} Kbps"
                return f"{bps} bps"

            active = api.get_resource('/ip/hotspot/active').get()
            active_count = len(active) if active else 0

            text = (
                f"📈 **Live WAN Bandwidth Monitor**\n\n"
                f"🌐 **Interface:** `ACL_WAN`\n"
                f"📥 **Download (Rx):** `{fmt_speed(rx_bps)}`\n"
                f"📤 **Upload (Tx):** `{fmt_speed(tx_bps)}`\n"
                f"👥 **Connected Users Right Now:** `{active_count}`"
            )
            bot.edit_message_text(text, chat_id=message.chat.id, message_id=msg.message_id, parse_mode="Markdown")
        except Exception as e:
            bot.edit_message_text(f"⚠️ Error reading live bandwidth: {e}", chat_id=message.chat.id, message_id=msg.message_id)
        finally:
            pool.disconnect()

    @bot.message_handler(commands=['blocked', 'blacklist'])
    def blocked_ips_cmd(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        msg = bot.reply_to(message, "⏳ Fetching firewall blacklist from router...")
        pool = mikrotik.connect()
        if not pool:
            bot.edit_message_text("⚠️ Could not connect to MikroTik router.", chat_id=message.chat.id, message_id=msg.message_id)
            return
        try:
            api = pool.get_api()
            addr_resource = api.get_resource('/ip/firewall/address-list')
            temp_list = addr_resource.get(list='login-blocked')
            perm_list = addr_resource.get(list='login-perm-blocked')

            text = "🛡️ **Firewall Blacklisted IPs**\n\n"
            if temp_list:
                text += "⏱️ **Temporary (1-Hour Ban):**\n"
                for item in temp_list:
                    ip = item.get('address')
                    timeout = item.get('timeout', '1h')
                    text += f"• `{ip}` (Expires: {timeout})\n"
                text += "\n"
            else:
                text += "⏱️ No temporary 1-hour bans active.\n\n"

            if perm_list:
                text += "🔒 **Permanent (Botnet/Repeat Bans):**\n"
                for item in perm_list:
                    ip = item.get('address')
                    comment = item.get('comment', 'Botnet')
                    text += f"• `{ip}` — _{comment}_\n"
            else:
                text += "🔒 No permanent bans active.\n"

            text += "\n✏️ _To unblock an IP, use:_ `/unblock <ip>`"
            bot.edit_message_text(text, chat_id=message.chat.id, message_id=msg.message_id, parse_mode="Markdown")
        except Exception as e:
            bot.edit_message_text(f"⚠️ Error reading blacklist: {e}", chat_id=message.chat.id, message_id=msg.message_id)
        finally:
            pool.disconnect()

    @bot.message_handler(commands=['unblock'])
    def unblock_ip_cmd(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "Usage: `/unblock <ip_address>`", parse_mode="Markdown")
            return
        ip = args[1].strip()
        pool = mikrotik.connect()
        if not pool:
            bot.reply_to(message, "⚠️ Could not connect to MikroTik router.")
            return
        try:
            api = pool.get_api()
            addr_resource = api.get_resource('/ip/firewall/address-list')
            found = False
            for item in addr_resource.get(address=ip):
                if item.get('list') in ('login-blocked', 'login-perm-blocked'):
                    addr_resource.remove(id=item.get('id'))
                    found = True
            if found:
                bot.reply_to(message, f"✅ Successfully unblocked `{ip}` from router firewall.", parse_mode="Markdown")
            else:
                bot.reply_to(message, f"ℹ️ IP `{ip}` was not found in the blacklist.", parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"⚠️ Error unblocking IP: {e}")
        finally:
            pool.disconnect()

    @bot.message_handler(commands=['find', 'search', 'user'])
    def find_user_cmd(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "Usage: `/find <phone_or_username>`", parse_mode="Markdown")
            return
        query = sanitize_username(args[1].strip())
        try:
            user = db.get_user_by_username(query)
            if not user:
                # Check if searched by phone
                all_u = db.get_all_users()
                for u in all_u:
                    if u.get('phone') == query:
                        user = u
                        break
            if not user:
                bot.reply_to(message, f"🔍 No user found for `{query}`.", parse_mode="Markdown")
                return

            username = user.get('username')
            phone = user.get('phone')
            password = user.get('password')
            pkg = user.get('package', 'N/A')
            approved = "Approved ✅" if user.get('approved') else "Pending Approval ⏳"

            exp_str = "Not set"
            days_left = ""
            if user.get('expiration_timestamp'):
                exp_time = parse_isoformat(user.get('expiration_timestamp'))
                if exp_time:
                    exp_str = exp_time.strftime('%Y-%m-%d %H:%M')
                    diff = (exp_time - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
                    if diff > 0:
                        days = int(diff // 86400)
                        hours = int((diff % 86400) // 3600)
                        days_left = f"({days}d {hours}h remaining)"
                    else:
                        days_left = "(Expired ❌)"

            # Check if online on router
            online_status = "Offline ⚪"
            active_sessions = mikrotik.get_active_users()
            for s in active_sessions:
                if s.get('user') == username:
                    online_status = f"Online 🟢 (IP: {s.get('address')}, Uptime: {s.get('uptime')})"
                    break

            text = (
                f"👤 **Customer Profile: `{username}`**\n\n"
                f"📱 **Phone:** `{phone}`\n"
                f"🔑 **Password:** `{password}`\n"
                f"📦 **Package:** `{pkg}`\n"
                f"🚦 **Status:** {approved}\n"
                f"⏳ **Expires:** `{exp_str}` {days_left}\n"
                f"📶 **Live Session:** {online_status}"
            )
            bot.reply_to(message, text, parse_mode="Markdown", reply_markup=get_user_actions_keyboard(username))
        except Exception as e:
            bot.reply_to(message, f"Database error: {e}")

    @bot.message_handler(commands=['extend'])
    def extend_user_cmd(message):
        if message.chat.id != TELEGRAM_CHAT_ID:
            return
        args = message.text.split()
        if len(args) < 3:
            bot.reply_to(message, "Usage: `/extend <username> <days>`\nExample: `/extend 01712345678 15`", parse_mode="Markdown")
            return
        username = sanitize_username(args[1].strip())
        try:
            days = int(args[2].strip())
        except ValueError:
            bot.reply_to(message, "Days must be a positive number.")
            return

        user = db.get_user_by_username(username)
        if not user:
            bot.reply_to(message, f"User `{username}` not found.", parse_mode="Markdown")
            return

        current_exp = parse_isoformat(user.get('expiration_timestamp'))
        now = datetime.datetime.now(datetime.timezone.utc)
        base_time = current_exp if (current_exp and current_exp > now) else now
        new_exp = base_time + datetime.timedelta(days=days)

        db.update_user(username, {
            "approved": True,
            "expiration_timestamp": new_exp.isoformat()
        })
        # Ensure user enabled on router
        mikrotik.enable_hotspot_user(username)
        bot.reply_to(
            message,
            f"✅ Extended `{username}` by **{days} days**.\n⏳ **New Expiration:** `{new_exp.strftime('%Y-%m-%d')}`",
            parse_mode="Markdown"
        )

    # --- Extended Button Handlers ---
    @bot.message_handler(func=lambda m: m.text == "💰 Sales Report")
    def text_sales(m): sales_report_cmd(m)

    @bot.message_handler(func=lambda m: m.text == "📈 Live Traffic")
    def text_traffic(m): traffic_monitor_cmd(m)

    @bot.message_handler(func=lambda m: m.text == "🛡️ Blocked IPs")
    def text_blocked(m): blocked_ips_cmd(m)

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
