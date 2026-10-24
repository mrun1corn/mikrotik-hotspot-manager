from telebot import TeleBot
from backend.config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, logger

bot_token = TELEGRAM_BOT_TOKEN if (TELEGRAM_BOT_TOKEN and ':' in TELEGRAM_BOT_TOKEN) else '000000000:dummy_token_for_init'
bot = TeleBot(bot_token, threaded=False)

def notify_admin_error(context, error):
    """Send error notification to admin via Telegram."""
    try:
        if TELEGRAM_CHAT_ID and bot_token != '000000000:dummy_token_for_init':
            bot.send_message(TELEGRAM_CHAT_ID, f"⚠️ Error in {context}:\n{str(error)[:500]}")
    except Exception as e:
        logger.error(f"Failed to notify admin about error in {context}: {e}")
