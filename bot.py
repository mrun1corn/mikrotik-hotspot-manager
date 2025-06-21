import asyncio
import random
import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from routeros_api import RouterOsApiPool
import json

with open("config.json", "r") as f:
    config = json.load(f)

API_TOKEN = config["telegram"]["bot_token"]
ADMIN_CHAT_ID = config["telegram"]["admin_chat_id"]

MIKROTIK_IP = config["mikrotik"]["host"]
MIKROTIK_USER = config["mikrotik"]["user"]
MIKROTIK_PASS = config["mikrotik"]["pass"]
MIKROTIK_API_PORT = config["mikrotik"]["port"]



def get_expiry(package):
    durations = {
        "1_day": 1,
        "7_days": 7,
        "30_days": 30
    }
    days = durations.get(package, 1)
    expiry_date = datetime.datetime.now() + datetime.timedelta(days=days)
    return expiry_date.strftime("%Y-%m-%d")


async def approve_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        # Expected format: approve|bkash|trx|ip|package
        data = query.data.split('|')
        if len(data) != 5:
            await query.edit_message_text("❌ Invalid approval data.")
            return

        _, bkash, trx, ip, package = data

        username = f"user{random.randint(1000,9999)}"
        password = f"{random.randint(100000,999999)}"
        expiry = get_expiry(package)

        api_pool = RouterOsApiPool(
            MIKROTIK_IP,
            username=MIKROTIK_USER,
            password=MIKROTIK_PASS,
            port=MIKROTIK_API_PORT,
            plaintext_login=True
        )
        api = api_pool.get_api()
        user_resource = api.get_resource('/ip/hotspot/user')

        user_resource.add(
            name=username,
            password=password,
            profile=package,
            comment=f"{bkash} | {trx} | {expiry}"
        )
        api_pool.disconnect()

        await query.edit_message_text(
            f"✅ *User Approved!*\n\n"
            f"👤 *Username:* `{username}`\n"
            f"🔐 *Password:* `{password}`\n"
            f"📦 *Package:* `{package}`\n"
            f"📅 *Valid Till:* `{expiry}`\n"
            f"🌐 *IP:* `{ip}`",
            parse_mode='Markdown'
        )

    except Exception as e:
        await query.edit_message_text(f"❌ Error approving user:\n`{e}`", parse_mode='Markdown')


# Existing commands below

async def approve(update, context):
    try:
        bkash_number, trx_id, ip = context.args
    except Exception:
        await update.message.reply_text("Usage: /approve <bkash_number> <trx_id> <ip>")
        return

    username = f"user{random.randint(1000,9999)}"
    password = f"{random.randint(100000,999999)}"

    try:
        api_pool = RouterOsApiPool(
            MIKROTIK_IP,
            username=MIKROTIK_USER,
            password=MIKROTIK_PASS,
            port=MIKROTIK_API_PORT,
            plaintext_login=True
        )
        api = api_pool.get_api()
        user_resource = api.get_resource('/ip/hotspot/user')
        user_resource.add(name=username, password=password, profile='default')
        api_pool.disconnect()

        await update.message.reply_text(
            f"✅ Approved!\nUser added:\n\nUsername: `{username}`\nPassword: `{password}`\n\nIP: {ip}",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def active_users(update, context):
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
            await update.message.reply_text("No active hotspot users currently.")
            return

        msg = "*Active Hotspot Users:*\n"
        for u in active_users:
            user = u.get('user')
            ip = u.get('address')
            uptime = u.get('uptime')
            msg += f"• `{user}` - IP: {ip}, Uptime: {uptime}\n"

        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def usage(update, context):
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
                    f"Usage for `{username}`:\nUpload: {tx_mb:.2f} MB\nDownload: {rx_mb:.2f} MB",
                    parse_mode='Markdown'
                )
                return
        await update.message.reply_text(f"No active user found with username `{username}`.", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def help_command(update, context):
    msg = (
        "Available commands:\n"
        "/approve <bkash> <trx_id> <ip> - Approve manually\n"
        "/activeusers - List active hotspot users\n"
        "/usage <username> - Show user traffic\n"
        "/help - Show this help message"
    )
    await update.message.reply_text(msg)


async def startup_notify(app):
    try:
        api_pool = RouterOsApiPool(
            MIKROTIK_IP,
            username=MIKROTIK_USER,
            password=MIKROTIK_PASS,
            port=MIKROTIK_API_PORT,
            plaintext_login=True
        )
        api = api_pool.get_api()
        api_pool.disconnect()
        await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text="✅ Bot started and connected to MikroTik.")
    except Exception as e:
        await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"⚠️ Bot started but failed to connect MikroTik:\n{e}")


def main():
    app = ApplicationBuilder().token(API_TOKEN).build()

    # Handlers
    app.add_handler(CallbackQueryHandler(approve_inline, pattern="^approve\\|"))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("activeusers", active_users))
    app.add_handler(CommandHandler("usage", usage))
    app.add_handler(CommandHandler("help", help_command))

    asyncio.get_event_loop().create_task(startup_notify(app))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
