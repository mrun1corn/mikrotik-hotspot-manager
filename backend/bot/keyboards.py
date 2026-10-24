from telebot import types

def get_admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("📊 System Status"),
        types.KeyboardButton("🚨 Security Logs"),
        types.KeyboardButton("📦 Manage Packages"),
        types.KeyboardButton("👥 Active Users"),
        types.KeyboardButton("⏳ Pending Approvals"),
        types.KeyboardButton("⚙️ Router Sync"),
        types.KeyboardButton("🔄 Reboot Router"),
        types.KeyboardButton("ℹ️ Help")
    )
    return markup

def get_reboot_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("Yes, Reboot", callback_data="reboot_confirm"),
        types.InlineKeyboardButton("Cancel", callback_data="reboot_cancel")
    )
    return keyboard

def get_approval_keyboard(username):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("Approve", callback_data=f"approve_{username}"),
        types.InlineKeyboardButton("Reject", callback_data=f"reject_{username}")
    )
    return keyboard

def get_speed_keyboard(profile_name):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    speeds = ["1M/1M", "2M/2M", "3M/3M", "5M/5M", "10M/10M"]
    buttons = [types.InlineKeyboardButton(s, callback_data=f"spd_{profile_name}_{s}") for s in speeds]
    keyboard.add(*buttons)
    keyboard.add(types.InlineKeyboardButton("✏️ Custom Limit", callback_data=f"custom_{profile_name}"))
    keyboard.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_pkg"))
    return keyboard
