import datetime
from telebot import types

from backend.config.settings import TELEGRAM_CHAT_ID, logger
from backend.bot.instance import bot, notify_admin_error
from backend.bot.keyboards import get_speed_keyboard
from backend.mikrotik import mikrotik
from backend.database import db
from backend.security import sanitize_username, parse_isoformat

def register_callback_handlers():
    @bot.callback_query_handler(func=lambda call: True)
    def callback_query(call):
        try:
            if call.from_user.id != TELEGRAM_CHAT_ID:
                bot.answer_callback_query(call.id, "You are not authorized to perform this action.")
                return

            if call.data.startswith("custom_"):
                profile_name = call.data[7:]
                bot.edit_message_text(
                    f"✏️ **To set a custom limit for `{profile_name}`**, simply copy and paste the command below into the chat, and change the `3M/3M` to your desired speed:\n\n`/setlimit {profile_name} 3M/3M`",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode="Markdown"
                )
                return

            if call.data == "reboot_confirm":
                bot.edit_message_text("🔄 Rebooting MikroTik router...", chat_id=call.message.chat.id, message_id=call.message.message_id)
                if mikrotik.reboot_router():
                    bot.send_message(TELEGRAM_CHAT_ID, "✅ Reboot command sent successfully!")
                else:
                    bot.send_message(TELEGRAM_CHAT_ID, "⚠️ Failed to send reboot command.")
                return

            if call.data == "reboot_cancel":
                bot.edit_message_text("❌ Reboot cancelled.", chat_id=call.message.chat.id, message_id=call.message.message_id)
                return

            if call.data == "cancel_pkg":
                bot.edit_message_text("❌ Package edit cancelled.", chat_id=call.message.chat.id, message_id=call.message.message_id)
                return

            if call.data.startswith("pkg_"):
                profile_name = call.data[4:]
                keyboard = get_speed_keyboard(profile_name)
                bot.edit_message_text(
                    f"🚀 **Select new speed limit for `{profile_name}`:**", 
                    chat_id=call.message.chat.id, 
                    message_id=call.message.message_id, 
                    parse_mode="Markdown", 
                    reply_markup=keyboard
                )
                return

            if call.data.startswith("spd_"):
                parts = call.data.split('_', 2)
                if len(parts) == 3:
                    profile_name = parts[1]
                    new_limit = parts[2]
                    bot.edit_message_text(
                        f"⏳ Updating `{profile_name}` to {new_limit}...", 
                        chat_id=call.message.chat.id, 
                        message_id=call.message.message_id, parse_mode="Markdown"
                    )
                    if mikrotik.set_profile_limit(profile_name, new_limit):
                        bot.edit_message_text(
                            f"✅ **Success!**\nPackage `{profile_name}` is now limited to `{new_limit}`.", 
                            chat_id=call.message.chat.id, 
                            message_id=call.message.message_id, parse_mode="Markdown"
                        )
                    else:
                        bot.edit_message_text(
                            f"⚠️ Failed to update `{profile_name}`.", 
                            chat_id=call.message.chat.id, 
                            message_id=call.message.message_id, parse_mode="Markdown"
                        )
                return

            if call.data.startswith("actkick_"):
                user = sanitize_username(call.data[8:])
                if mikrotik.kick_user(user):
                    bot.answer_callback_query(call.id, f"Kicked {user}")
                    bot.send_message(TELEGRAM_CHAT_ID, f"👢 Kicked active session for `{user}`.", parse_mode="Markdown")
                else:
                    bot.answer_callback_query(call.id, "Session not found")
                return

            if call.data.startswith("actdel_"):
                user = sanitize_username(call.data[7:])
                db.delete_user(user)
                mikrotik.delete_hotspot_user(user)
                bot.answer_callback_query(call.id, f"Deleted {user}")
                bot.send_message(TELEGRAM_CHAT_ID, f"🗑 User `{user}` deleted from DB and router.", parse_mode="Markdown")
                return

            if call.data.startswith("actext_"):
                parts = call.data.split('_')
                if len(parts) >= 3:
                    try:
                        days = int(parts[1])
                        user = sanitize_username('_'.join(parts[2:]))
                        u_data = db.get_user_by_username(user)
                        if u_data:
                            current_exp = parse_isoformat(u_data.get('expiration_timestamp'))
                            now = datetime.datetime.now(datetime.timezone.utc)
                            base_time = current_exp if (current_exp and current_exp > now) else now
                            new_exp = base_time + datetime.timedelta(days=days)
                            db.update_user(user, {"approved": True, "expiration_timestamp": new_exp.isoformat()})
                            mikrotik.enable_hotspot_user(user)
                            bot.answer_callback_query(call.id, f"Extended +{days} days")
                            bot.send_message(TELEGRAM_CHAT_ID, f"⏳ Extended `{user}` by **+{days} days**.\nExpires: `{new_exp.strftime('%Y-%m-%d')}`", parse_mode="Markdown")
                        else:
                            bot.answer_callback_query(call.id, "User not found")
                    except Exception as e:
                        logger.error(f"Extend error: {e}")
                        bot.answer_callback_query(call.id, "Error extending user")
                return

            if '_' not in call.data:
                bot.answer_callback_query(call.id, "Invalid action.")
                return

            action, username = call.data.split('_', 1)
            username = sanitize_username(username)

            if action not in ("approve", "reject"):
                bot.answer_callback_query(call.id, "Unknown action.")
                return

            user_data = db.get_user_by_username(username)
            if not user_data:
                bot.answer_callback_query(call.id, "User data not found.")
                return

            if action == "approve":
                if user_data["approved"]:
                    bot.answer_callback_query(call.id, "User already approved.")
                    return

                if mikrotik.add_hotspot_user(username, user_data["password"], user_data["package"]) and \
                   mikrotik.enable_hotspot_user(username):

                    expiration_days = 15 if user_data["package"] == "15_days_40_tk" else 30
                    approval_time = datetime.datetime.now(datetime.timezone.utc)
                    expiration_time = approval_time + datetime.timedelta(days=expiration_days)

                    db.update_user(username, {
                        "approved": True,
                        "approval_timestamp": approval_time.isoformat(),
                        "expiration_timestamp": expiration_time.isoformat()
                    })

                    # Instantly authorize the connected device on the router so internet starts immediately
                    mikrotik.login_active_host(username, user_data["password"])

                    bot.answer_callback_query(call.id, f"User {username} approved and enabled.")
                    try:
                        bot.edit_message_caption(
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                            caption=call.message.caption + "\n\n✅ Approved!",
                            reply_markup=None
                        )
                    except Exception:
                        pass
                    bot.send_message(TELEGRAM_CHAT_ID, f"User {username} approved. Expires {expiration_time.strftime('%Y-%m-%d')}.")
                else:
                    bot.answer_callback_query(call.id, f"Failed to add/enable user {username} in MikroTik.")
                    notify_admin_error("approve/mikrotik", f"MikroTik add/enable failed for {username}")

            elif action == "reject":
                if user_data["approved"]:
                    bot.answer_callback_query(call.id, "Cannot reject an already approved user.")
                    return

                db.delete_user(username)
                bot.answer_callback_query(call.id, f"User {username} rejected and removed.")
                try:
                    bot.edit_message_caption(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        caption=call.message.caption + "\n\n❌ Rejected!",
                        reply_markup=None
                    )
                except Exception:
                    pass
                bot.send_message(TELEGRAM_CHAT_ID, f"User {username} has been rejected and removed.")

        except Exception as e:
            logger.error(f"Callback query error: {e}", exc_info=True)
            try:
                bot.answer_callback_query(call.id, "An error occurred. Check logs.")
            except Exception:
                pass
