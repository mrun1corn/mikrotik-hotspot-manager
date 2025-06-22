import asyncio
import datetime
import json
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)
from routeros_api import RouterOsApiPool

# Load config
with open("config.json", "r") as f:
    config = json.load(f)

API_TOKEN = config["telegram"]["bot_token"]
ADMIN_CHAT_ID = config["telegram"]["admin_chat_id"]

MIKROTIK_IP = config["mikrotik"]["host"]
MIKROTIK_USER = config["mikrotik"]["user"]
MIKROTIK_PASS = config["mikrotik"]["pass"]
MIKROTIK_API_PORT = config["mikrotik"]["port"]

PENDING_DIR = "pending_users"

def get_expiry(package, approval_time=None):
    durations = {
        "1_day": 1,
        "7_days": 7,
        "30_days": 30
    }
    days = durations.get(package.lower(), 1)  # Normalize case, default to 1 day
    if package.lower() not in durations:
        print(f"Warning: Unknown package '{package}', defaulting to 1 day")
        with open("error_log.txt", "a") as f:
            f.write(f"{datetime.datetime.now()}: Warning: Unknown package '{package}', defaulting to 1 day\n")
    # Use provided approval time or current time
    approval_time = approval_time or datetime.datetime.now()
    expiry_time = approval_time + datetime.timedelta(days=days)
    # Format for MikroTik scheduler (e.g., jun/23/2025 13:00:00)
    mikrotik_format = expiry_time.strftime("%b/%d/%Y %H:%M:%S").lower()
    # Format for display (e.g., 2025-06-23 13:00)
    display_format = expiry_time.strftime("%Y-%m-%d %H:%M")
    return expiry_time, mikrotik_format, display_format

async def approve_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        # Expected format: approve|bkash|username|ip|package
        data = query.data.split('|')
        if len(data) != 5:
            error_msg = "❌ Invalid approval data format."
            print(error_msg)
            with open("error_log.txt", "a") as f:
                f.write(f"{datetime.datetime.now()}: {error_msg}\n")
            await query.edit_message_caption(caption=error_msg, parse_mode="Markdown")
            return

        _, bkash, username, ip, package = data
        json_file = os.path.join(PENDING_DIR, f"{username}.json")

        # Step 1: Load user data from file
        if not os.path.exists(json_file):
            error_msg = f"❌ No pending user found for username: {username}"
            print(error_msg)
            with open("error_log.txt", "a") as f:
                f.write(f"{datetime.datetime.now()}: {error_msg}\n")
            await query.edit_message_caption(caption=error_msg, parse_mode="Markdown")
            return

        with open(json_file, 'r') as f:
            user_data = json.load(f)

        file_username = user_data["username"]
        password = str(user_data["password"])  # Ensure string
        file_ip = user_data["ip"]
        file_package = user_data["package"]

        # Verify input data matches file
        if ip != file_ip or package.lower() != file_package.lower() or username != file_username:
            error_msg = f"❌ Mismatch in user data: Username ({username} vs {file_username}), IP ({ip} vs {file_ip}) or Package ({package} vs {file_package})"
            print(error_msg)
            with open("error_log.txt", "a") as f:
                f.write(f"{datetime.datetime.now()}: {error_msg}\n")
            await query.edit_message_caption(caption=error_msg, parse_mode="Markdown")
            return

        # Step 2: Connect to MikroTik
        api_pool = RouterOsApiPool(
            MIKROTIK_IP,
            username=MIKROTIK_USER,
            password=MIKROTIK_PASS,
            port=MIKROTIK_API_PORT,
            plaintext_login=True
        )
        api = api_pool.get_api()
        user_resource = api.get_resource("/ip/hotspot/user")
        script_resource = api.get_resource("/system/script")
        scheduler_resource = api.get_resource("/system/scheduler")

        # Fetch user by username
        users = user_resource.get(name=username)
        print(f"Users found for {username}: {users}")
        with open("error_log.txt", "a") as f:
            f.write(f"{datetime.datetime.now()}: Users found for {username}: {users}\n")
        if not users:
            error_msg = f"❌ User {username} not found in MikroTik."
            print(error_msg)
            with open("error_log.txt", "a") as f:
                f.write(f"{datetime.datetime.now()}: {error_msg}\n")
            await query.edit_message_caption(caption=error_msg, parse_mode="Markdown")
            api_pool.disconnect()
            return

        user = users[0]
        user_id = user.get('id')
        if not user_id:
            error_msg = f"❌ Could not retrieve user ID for {username}. User data: {user}"
            print(error_msg)
            with open("error_log.txt", "a") as f:
                f.write(f"{datetime.datetime.now()}: {error_msg}\n")
            await query.edit_message_caption(caption=error_msg, parse_mode="Markdown")
            api_pool.disconnect()
            return

        # Verify user is disabled (accept 'true' or 'yes')
        if user.get("disabled") not in ["true", "yes"]:
            error_msg = f"❌ User {username} is already enabled or in an unexpected state: {user.get('disabled')}"
            print(error_msg)
            with open("error_log.txt", "a") as f:
                f.write(f"{datetime.datetime.now()}: {error_msg}\n")
            await query.edit_message_caption(caption=error_msg, parse_mode="Markdown")
            api_pool.disconnect()
            return

        # Verify user data matches (case-insensitive)
        mikrotik_password = user.get("password") or ""  # Handle missing password
        mikrotik_profile = user.get("profile") or ""    # Handle missing profile
        if mikrotik_password != password or mikrotik_profile.lower() != package.lower():
            error_msg = (
                f"❌ User data mismatch for {username}: "
                f"Password (MikroTik: '{mikrotik_password}' vs JSON: '{password}'), "
                f"Profile (MikroTik: '{mikrotik_profile}' vs JSON: '{package}')"
            )
            print(error_msg)
            with open("error_log.txt", "a") as f:
                f.write(f"{datetime.datetime.now()}: {error_msg}\n")
            await query.edit_message_caption(caption=error_msg, parse_mode="Markdown")
            api_pool.disconnect()
            return

        # Step 3: Calculate expiry time
        approval_time = datetime.datetime.now()
        expiry_time, mikrotik_expiry, display_expiry = get_expiry(package, approval_time)

        # Clean up existing script and scheduler if they exist
        try:
            existing_scripts = script_resource.get(name=f"remove-user-{username}")
            if existing_scripts:
                script_resource.remove(id=existing_scripts[0].get("id"))
        except:
            pass  # Ignore if script doesn't exist
        try:
            existing_schedulers = scheduler_resource.get(name=f"expire-user-{username}")
            if existing_schedulers:
                scheduler_resource.remove(id=existing_schedulers[0].get("id"))
        except:
            pass  # Ignore if scheduler doesn't exist

        # Create removal script
        script_name = f"remove-user-{username}"
        script_content = f"/ip hotspot user remove [find name={username}]"
        try:
            script_resource.add(
                **{
                    "name": script_name,
                    "source": script_content,
                    "policy": "read,write",
                    "dont-require-permissions": "yes"
                }
            )
        except Exception as e:
            error_msg = f"❌ Failed to create script for {username}: {str(e)}"
            print(error_msg)
            with open("error_log.txt", "a") as f:
                f.write(f"{datetime.datetime.now()}: {error_msg}\n")
            await query.edit_message_caption(caption=error_msg, parse_mode="Markdown")
            api_pool.disconnect()
            return

        # Create scheduler
        scheduler_name = f"expire-user-{username}"
        try:
            scheduler_resource.add(
                **{
                    "name": scheduler_name,
                    "start-date": mikrotik_expiry.split(" ")[0],  # e.g., jun/23/2025
                    "start-time": mikrotik_expiry.split(" ")[1],  # e.g., 13:00:00
                    "interval": "0",  # Run once
                    "on-event": script_name,
                    "policy": "read,write",
                    "disabled": "no"
                }
            )
        except Exception as e:
            # Cleanup script if scheduler creation fails
            try:
                script_resource.remove(name=script_name)
            except:
                pass
            error_msg = f"❌ Failed to create scheduler for {username}: {str(e)}"
            print(error_msg)
            with open("error_log.txt", "a") as f:
                f.write(f"{datetime.datetime.now()}: {error_msg}\n")
            await query.edit_message_caption(caption=error_msg, parse_mode="Markdown")
            api_pool.disconnect()
            return

        # Get scheduler ID
        schedulers = scheduler_resource.get(name=scheduler_name)
        scheduler_id = schedulers[0].get("id") if schedulers else ""

        # Step 4: Enable user and update comment
        try:
            user_resource.set(
                **{
                    "id": user_id,
                    "disabled": "false",
                    "comment": f"{bkash} | {display_expiry} | scheduler={scheduler_id}"
                }
            )
        except Exception as e:
            # Cleanup script and scheduler if user update fails
            try:
                script_resource.remove(name=script_name)
            except:
                pass
            try:
                if scheduler_id:
                    scheduler_resource.remove(id=scheduler_id)
            except:
                pass
            error_msg = f"❌ Failed to enable user {username}: {str(e)}"
            print(error_msg)
            with open("error_log.txt", "a") as f:
                f.write(f"{datetime.datetime.now()}: {error_msg}\n")
            await query.edit_message_caption(caption=error_msg, parse_mode="Markdown")
            api_pool.disconnect()
            return

        # Verify update
        updated_user = user_resource.get(name=username)
        api_pool.disconnect()

        if updated_user and updated_user[0].get("disabled") in ["false", "no"]:
            # Delete pending file only if update was successful
            os.remove(json_file)
            success_msg = (
                f"✅ *User Approved!*\n\n"
                f"👤 *Username:* `{username}`\n"
                f"🔐 *Password:* `{password}`\n"
                f"📦 *Package:* `{package}`\n"
                f"📅 *Valid Till:* `{display_expiry}`\n"
                f"🌐 *IP:* `{ip}`"
            )
            print(f"User {username} approved successfully")
            with open("error_log.txt", "a") as f:
                f.write(f"{datetime.datetime.now()}: User {username} approved successfully\n")
            await query.edit_message_caption(caption=success_msg, parse_mode="Markdown")
        else:
            # Cleanup script and scheduler if verification fails
            try:
                script_resource.remove(name=script_name)
            except:
                pass
            try:
                if scheduler_id:
                    scheduler_resource.remove(id=scheduler_id)
            except:
                pass
            error_msg = f"❌ Failed to verify user {username} enablement. Updated data: {updated_user}"
            print(error_msg)
            with open("error_log.txt", "a") as f:
                f.write(f"{datetime.datetime.now()}: {error_msg}\n")
            await query.edit_message_caption(caption=error_msg, parse_mode="Markdown")

    except Exception as e:
        error_msg = f"❌ Error approving user: {str(e)}"
        print(error_msg)
        with open("error_log.txt", "a") as f:
            f.write(f"{datetime.datetime.now()}: {error_msg}\n")
        await query.edit_message_caption(caption=error_msg, parse_mode="Markdown")

async def reject_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        # Expected format: reject|bkash|username|ip|package
        data = query.data.split('|')
        if len(data) != 5:
            error_msg = "❌ Invalid reject data format."
            print(error_msg)
            with open("error_log.txt", "a") as f:
                f.write(f"{datetime.datetime.now()}: {error_msg}\n")
            await query.edit_message_caption(caption=error_msg, parse_mode="Markdown")
            return

        _, bkash, username, ip, package = data
        json_file = os.path.join(PENDING_DIR, f"{username}.json")

        # Check if pending user exists
        if not os.path.exists(json_file):
            error_msg = f"❌ No pending user found for username: {username}"
            print(error_msg)
            with open("error_log.txt", "a") as f:
                f.write(f"{datetime.datetime.now()}: {error_msg}\n")
            await query.edit_message_caption(caption=error_msg, parse_mode="Markdown")
            return

        # Connect to MikroTik
        api_pool = RouterOsApiPool(
            MIKROTIK_IP,
            username=MIKROTIK_USER,
            password=MIKROTIK_PASS,
            port=MIKROTIK_API_PORT,
            plaintext_login=True
        )
        api = api_pool.get_api()
        user_resource = api.get_resource("/ip/hotspot/user")

        # Delete user from MikroTik
        users = user_resource.get(name=username)
        if users:
            user_resource.remove(id=users[0].get("id"))

        # Delete pending file
        os.remove(json_file)
        api_pool.disconnect()

        success_msg = f"❌ *User Rejected!*\n\n👤 *Username:* `{username}`\n🌐 *IP:* `{ip}`\n📦 *Package:* `{package}`"
        print(f"User {username} rejected successfully")
        with open("error_log.txt", "a") as f:
            f.write(f"{datetime.datetime.now()}: User {username} rejected successfully\n")
        await query.edit_message_caption(caption=success_msg, parse_mode="Markdown")

    except Exception as e:
        error_msg = f"❌ Error rejecting user: {str(e)}"
        print(error_msg)
        with open("error_log.txt", "a") as f:
            f.write(f"{datetime.datetime.now()}: {error_msg}\n")
        await query.edit_message_caption(caption=error_msg, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚙️ *Commands:*\n"
        "/activeusers - List connected users\n"
        "/usage <username> - Show traffic\n"
        "/help - Show this message",
        parse_mode='Markdown'
    )

async def active_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        api_pool = RouterOsApiPool(
            MIKROTIK_IP,
            username=MIKROTIK_USER,
            password=MIKROTIK_PASS,
            port=MIKROTIK_API_PORT,
            plaintext_login=True
        )
        api = api_pool.get_api()
        active_users = api.get_resource('/ip/hotspot/active').get()
        api_pool.disconnect()

        if not active_users:
            await update.message.reply_text("No active users.")
            return

        msg = "*📶 Active Users:*\n"
        for u in active_users:
            user = u.get('user')
            ip = u.get('address')
            uptime = u.get('uptime')
            msg += f"• `{user}` - IP: {ip}, Uptime: {uptime}\n"

        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        print(error_msg)
        with open("error_log.txt", "a") as f:
            f.write(f"{datetime.datetime.now()}: {error_msg}\n")
        await update.message.reply_text(error_msg)

async def usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /usage <username>")
        return

    username = context.args[0]

    try:
        api_pool = RouterOsApiPool(
            MIKROTIK_IP,
            username=MIKROTIK_USER,
            password=MIKROTIK_PASS,
            port=MIKROTIK_API_PORT,
            plaintext_login=True
        )
        api = api_pool.get_api()
        active_users = api.get_resource('/ip/hotspot/active').get()
        api_pool.disconnect()

        for u in active_users:
            if u.get('user') == username:
                tx = int(u.get('bytes-out', 0))
                rx = int(u.get('bytes-in', 0))

                tx_mb = tx / (1024 * 1024)
                rx_mb = rx / (1024 * 1024)

                await update.message.reply_text(
                    f"📊 Usage for `{username}`:\n"
                    f"⬆️ Upload: {tx_mb:.2f} MB\n"
                    f"⬇️ Download: {rx_mb:.2f} MB",
                    parse_mode='Markdown'
                )
                return

        await update.message.reply_text(f"User `{username}` is not active.", parse_mode='Markdown')

    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        print(error_msg)
        with open("error_log.txt", "a") as f:
            f.write(f"{datetime.datetime.now()}: {error_msg}\n")
        await update.message.reply_text(error_msg)

async def startup_notify(app):
    try:
        api_pool = RouterOsApiPool(
            MIKROTIK_IP,
            username=MIKROTIK_USER,
            password=MIKROTIK_PASS,
            port=MIKROTIK_API_PORT,
            plaintext_login=True
        )
        api_pool.disconnect()
        await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text="✅ Bot is running and connected to MikroTik.")
    except Exception as e:
        error_msg = f"⚠️ Startup failed: {str(e)}"
        print(error_msg)
        with open("error_log.txt", "a") as f:
            f.write(f"{datetime.datetime.now()}: {error_msg}\n")
        await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=error_msg)

def main():
    app = ApplicationBuilder().token(API_TOKEN).build()

    app.add_handler(CallbackQueryHandler(approve_inline, pattern="^approve\\|"))
    app.add_handler(CallbackQueryHandler(reject_inline, pattern="^reject\\|"))
    app.add_handler(CommandHandler("activeusers", active_users))
    app.add_handler(CommandHandler("usage", usage))
    app.add_handler(CommandHandler("help", help_command))

    asyncio.get_event_loop().create_task(startup_notify(app))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
