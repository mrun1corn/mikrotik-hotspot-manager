import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Application Configuration ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')

# Supabase
SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')

# MikroTik
MIKROTIK_IP = os.getenv('MIKROTIK_IP', '')
MIKROTIK_USER = os.getenv('MIKROTIK_USER', '')
MIKROTIK_PASS = os.getenv('MIKROTIK_PASS', '')
MIKROTIK_API_PORT = int(os.getenv('MIKROTIK_API_PORT', 8728))
MIKROTIK_USE_SSL = os.getenv('MIKROTIK_USE_SSL', 'false').lower() in ('true', '1', 'yes')

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = int(os.getenv('TELEGRAM_CHAT_ID', 0))
TELEGRAM_WEBHOOK_SECRET = os.getenv('TELEGRAM_WEBHOOK_SECRET', '')

# Security & Cron
CRON_SECRET = os.getenv('CRON_SECRET', '')
SECRET_KEY = os.getenv('SECRET_KEY') or CRON_SECRET or SUPABASE_KEY or 'default-hotspot-secret-salt'
APP_URL = os.getenv('APP_URL', '')

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('hotspot_manager')
