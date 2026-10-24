from backend.bot.instance import bot, notify_admin_error
from backend.bot.keyboards import get_admin_keyboard, get_reboot_keyboard, get_approval_keyboard, get_speed_keyboard
from backend.bot.commands import register_command_handlers
from backend.bot.callbacks import register_callback_handlers

# Register all handlers on import
register_command_handlers()
register_callback_handlers()
