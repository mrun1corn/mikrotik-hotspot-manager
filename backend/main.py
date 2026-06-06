import requests
import os
import time
import datetime
import string
import secrets
import io
import re
import logging
from functools import wraps
from flask import Flask, request, render_template, send_file, url_for, jsonify
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from telebot import TeleBot, types
from routeros_api import RouterOsApiPool
from supabase import create_client, Client

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
MIKROTIK_IP = os.getenv('MIKROTIK_IP')
MIKROTIK_USER = os.getenv('MIKROTIK_USER')
MIKROTIK_PASS = os.getenv('MIKROTIK_PASS')
MIKROTIK_API_PORT = int(os.getenv('MIKROTIK_API_PORT', 8728))
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = int(os.getenv('TELEGRAM_CHAT_ID', 0))
CRON_SECRET = os.getenv('CRON_SECRET', '')

app = Flask(__name__, template_folder='templates')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

bot = TeleBot(TELEGRAM_BOT_TOKEN)

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Helper Functions ---
def parse_isoformat(dt_str):
    if not dt_str:
        return None
    if dt_str.endswith('Z'):
        dt_str = dt_str[:-1] + '+00:00'
    return datetime.datetime.fromisoformat(dt_str)

def sanitize_username(username):
    """Only allow alphanumeric, underscore, and dash."""
    return re.sub(r'[^a-zA-Z0-9_\-]', '', username)

def notify_admin_error(context, error):
    """Send error notification to admin via Telegram."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, f"⚠️ Error in {context}:\n{str(error)[:500]}")
    except Exception:
        logger.error(f"Failed to notify admin about error in {context}: {error}")

def require_cron_auth(f):
    """Protect cron endpoints from unauthorized access."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Vercel cron jobs send Authorization header automatically
        auth = request.headers.get('Authorization', '')
        cron_header = request.headers.get('x-vercel-cron', '')
        if cron_header:
            return f(*args, **kwargs)
        if CRON_SECRET and auth == f'Bearer {CRON_SECRET}':
            return f(*args, **kwargs)
        return 'Unauthorized', 401
    return decorated

# --- Global Error Handlers ---
@app.errorhandler(404)
def not_found(e):
    return render_template('register.html', message="Page not found.", message_type="error"), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal server error: {e}")
    return render_template('register.html', message="Something went wrong. Please try again later.", message_type="error"), 500

@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Unhandled exception: {e}", exc_info=True)
    return render_template('register.html', message="An unexpected error occurred.", message_type="error"), 500

# --- MikroTik API Interaction ---
class MikroTikAPI:
    def __init__(self, ip, user, password, port):
        self.ip = ip
        self.user = user
        self.password = password
        self.port = port

    def connect(self):
        """Establishes connection to MikroTik router."""
        try:
            pool = RouterOsApiPool(
                self.ip,
                username=self.user,
                password=self.password,
                port=self.port,
                plaintext_login=True
            )
            return pool
        except Exception as e:
            logger.error(f"MikroTik connection failed: {e}")
            return None

    def add_hotspot_user(self, username, password, package):
        """Adds a hotspot user with the package-specific profile."""
        pool = self.connect()
        if not pool:
            return False
        try:
            api = pool.get_api()
            users = api.get_resource('/ip/hotspot/user')

            profile_name = "default"
            if package == "15_days_40_tk":
                profile_name = "15-days-40TK"
            elif package == "30_days_100_tk":
                profile_name = "30-days-100TK"

            users.add(
                name=username,
                password=password,
                profile=profile_name,
                disabled='yes'
            )
            logger.info(f"MikroTik user '{username}' added (disabled), profile='{profile_name}'")
            return True
        except Exception as e:
            logger.error(f"Error adding MikroTik user '{username}': {e}")
            return False
        finally:
            pool.disconnect()

    def enable_hotspot_user(self, username):
        """Enables a hotspot user in MikroTik."""
        pool = self.connect()
        if not pool:
            return False
        try:
            api = pool.get_api()
            users = api.get_resource('/ip/hotspot/user')
            user = users.get(name=username)
            if user:
                users.set(id=user[0]['id'], disabled='no')
                logger.info(f"MikroTik user '{username}' enabled.")
                return True
            else:
                logger.warning(f"MikroTik user '{username}' not found for enabling.")
                return False
        except Exception as e:
            logger.error(f"Error enabling MikroTik user '{username}': {e}")
            return False
        finally:
            pool.disconnect()

    def delete_hotspot_user(self, username):
        """Deletes a hotspot user from MikroTik."""
        pool = self.connect()
        if not pool:
            return False
        try:
            api = pool.get_api()
            users = api.get_resource('/ip/hotspot/user')
            user = users.get(name=username)
            if user:
                users.remove(id=user[0]['id'])
                logger.info(f"MikroTik user '{username}' deleted.")
                return True
            else:
                logger.warning(f"MikroTik user '{username}' not found for deletion.")
                return False
        except Exception as e:
            logger.error(f"Error deleting MikroTik user '{username}': {e}")
            return False
        finally:
            pool.disconnect()

mikrotik = MikroTikAPI(MIKROTIK_IP, MIKROTIK_USER, MIKROTIK_PASS, MIKROTIK_API_PORT)

# --- Flask Web Server ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        package = request.form.get('package', '').strip()
        screenshot = request.files.get('screenshot')

        if not phone or not package or not screenshot:
            return render_template('register.html', message="All fields are required!", message_type="error")

        # Validate phone number
        if not phone.isdigit() or len(phone) < 10:
            return render_template('register.html', message="Invalid phone number.", message_type="error")

        # Validate package selection
        if package not in ("15_days_40_tk", "30_days_100_tk"):
            return render_template('register.html', message="Invalid package selected.", message_type="error")

        # Validate file type
        allowed_types = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
        if screenshot.content_type not in allowed_types:
            return render_template('register.html', message="Screenshot must be an image (JPG, PNG, WebP).", message_type="error")

        # Validate file size (max 5MB)
        screenshot_bytes = screenshot.read()
        if len(screenshot_bytes) > 5 * 1024 * 1024:
            return render_template('register.html', message="Screenshot must be under 5MB.", message_type="error")

        # Generate unique username
        base_username = phone
        username = base_username
        suffix = 0
        try:
            while True:
                res = supabase.table('users').select('username').eq('username', username).execute()
                if not res.data:
                    break
                suffix += 1
                username = f"{base_username}_{suffix}"
                if suffix > 100:
                    return render_template('register.html', message="Too many registrations for this phone number.", message_type="error")
        except Exception as e:
            logger.error(f"DB error checking username uniqueness: {e}")
            return render_template('register.html', message="Database error. Please try again.", message_type="error")

        # Generate cryptographically secure 6-digit numeric password
        password = ''.join(secrets.choice(string.digits) for _ in range(6))

        # Upload screenshot to Supabase Storage
        screenshot_filename = f"{username}_{int(time.time())}_{sanitize_username(screenshot.filename or 'screenshot.png')}"
        try:
            supabase.storage.from_('screenshots').upload(
                path=screenshot_filename,
                file=screenshot_bytes,
                file_options={"content-type": screenshot.content_type}
            )
            screenshot_url = supabase.storage.from_('screenshots').get_public_url(screenshot_filename)
        except Exception as e:
            logger.error(f"Screenshot upload failed: {e}")
            return render_template('register.html', message="Error processing payment screenshot.", message_type="error")

        # Store user info in Supabase
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        user_data = {
            "username": username,
            "phone": phone,
            "package": package,
            "password": password,
            "screenshot_url": screenshot_url,
            "registration_timestamp": now_str,
            "approved": False,
            "approval_timestamp": None,
            "expiration_timestamp": None,
            "telegram_message_id": None
        }

        try:
            supabase.table('users').insert(user_data).execute()
        except Exception as e:
            logger.error(f"DB insert failed for user '{username}': {e}")
            # Clean up uploaded screenshot
            try:
                supabase.storage.from_('screenshots').remove([screenshot_filename])
            except Exception:
                pass
            return render_template('register.html', message="Database error.", message_type="error")

        # Notify admin via Telegram
        caption = f"""New user registration request:
Phone: {phone}
Package: {package.replace('_', ' ').title()}
Username: {username}
Password: {password}"""
        keyboard = types.InlineKeyboardMarkup()
        approve_button = types.InlineKeyboardButton("Approve", callback_data=f"approve_{username}")
        reject_button = types.InlineKeyboardButton("Reject", callback_data=f"reject_{username}")
        keyboard.add(approve_button, reject_button)

        try:
            message = bot.send_photo(TELEGRAM_CHAT_ID, screenshot_url, caption=caption, reply_markup=keyboard)
            supabase.table('users').update({"telegram_message_id": message.message_id}).eq("username", username).execute()
        except Exception as e:
            logger.error(f"Telegram notification failed for '{username}': {e}")
            # Registration is saved but admin wasn't notified — flag it
            notify_admin_error("register/telegram", f"Registration saved but notification failed for {username}: {e}")

        return render_template(
            'success.html',
            username=username,
            password=password,
            download_link=url_for('download_credentials', username=username)
        )
    return render_template('register.html')

@app.route('/download/<username>')
def download_credentials(username):
    # Sanitize input to prevent path traversal
    username = sanitize_username(username)
    if not username:
        return "Invalid username", 400

    try:
        res = supabase.table('users').select('password').eq('username', username).execute()
    except Exception as e:
        logger.error(f"DB lookup failed for download '{username}': {e}")
        return "Service unavailable", 503

    if not res.data:
        return "User not found", 404
    user_data = res.data[0]

    username_text = f"Username: {username}"
    password_text = f"Password: {user_data['password']}"

    # Create image in memory
    img = Image.new('RGB', (400, 200), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except IOError:
        font = ImageFont.load_default()

    d.text((50, 70), username_text, fill=(0, 0, 0), font=font)
    d.text((50, 110), password_text, fill=(0, 0, 0), font=font)

    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)

    return send_file(img_io, mimetype='image/png', as_attachment=True, download_name=f"{username}_credentials.png")

# --- Telegram Bot Webhook & Handlers ---
@app.route('/api/webhook', methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') != 'application/json':
        return 'Forbidden', 403
    try:
        json_string = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_string)
        bot.process_new_updates([update])
    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
    # Always return 200 to prevent Telegram from retrying on errors
    return '', 200

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.id == TELEGRAM_CHAT_ID:
        bot.reply_to(message, "Welcome, admin! I'm ready to manage hotspot users via webhooks.")
    else:
        bot.reply_to(message, "You are not authorized to use this bot.")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    try:
        if call.from_user.id != TELEGRAM_CHAT_ID:
            bot.answer_callback_query(call.id, "You are not authorized to perform this action.")
            return

        # Safe split — handle malformed callback data
        if '_' not in call.data:
            bot.answer_callback_query(call.id, "Invalid action.")
            return
        action, username = call.data.split('_', 1)
        username = sanitize_username(username)

        if action not in ("approve", "reject"):
            bot.answer_callback_query(call.id, "Unknown action.")
            return

        res = supabase.table('users').select('*').eq('username', username).execute()
        if not res.data:
            bot.answer_callback_query(call.id, "User data not found.")
            return
        user_data = res.data[0]

        if action == "approve":
            if user_data["approved"]:
                bot.answer_callback_query(call.id, "User already approved.")
                return

            # Add and enable user in MikroTik
            if mikrotik.add_hotspot_user(username, user_data["password"], user_data["package"]) and \
               mikrotik.enable_hotspot_user(username):

                expiration_days = 15 if user_data["package"] == "15_days_40_tk" else 30
                approval_time = datetime.datetime.now(datetime.timezone.utc)
                expiration_time = approval_time + datetime.timedelta(days=expiration_days)

                supabase.table('users').update({
                    "approved": True,
                    "approval_timestamp": approval_time.isoformat(),
                    "expiration_timestamp": expiration_time.isoformat()
                }).eq("username", username).execute()

                bot.answer_callback_query(call.id, f"User {username} approved and enabled.")
                try:
                    bot.edit_message_caption(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        caption=call.message.caption + "\n\n✅ Approved!",
                        reply_markup=None
                    )
                except Exception:
                    pass  # Message may have been edited already
                bot.send_message(TELEGRAM_CHAT_ID, f"User {username} approved. Expires {expiration_time.strftime('%Y-%m-%d')}.")
            else:
                bot.answer_callback_query(call.id, f"Failed to add/enable user {username} in MikroTik.")
                notify_admin_error("approve/mikrotik", f"MikroTik add/enable failed for {username}")

        elif action == "reject":
            if user_data["approved"]:
                bot.answer_callback_query(call.id, "Cannot reject an already approved user.")
                return

            # Delete screenshot
            try:
                screenshot_filename = user_data["screenshot_url"].split('/')[-1]
                supabase.storage.from_('screenshots').remove([screenshot_filename])
            except Exception as e:
                logger.warning(f"Screenshot cleanup failed for '{username}': {e}")

            supabase.table('users').delete().eq("username", username).execute()

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

# --- Cron Job Expiration Checker Route ---
@app.route('/')
@app.route('/status')
def status_dashboard():
    # 1. Check MikroTik
    mt_status = "Not Connected"
    mt_uptime = "Unknown"
    pool = mikrotik.connect()
    if pool:
        try:
            api = pool.get_api()
            res = api.get_resource('/system/resource').get()
            if res:
                mt_uptime = res[0].get('uptime', 'Unknown')
                mt_status = "Connected ✅"
        except Exception as e:
            mt_status = f"Error: {e}"
        finally:
            pool.disconnect()
    else:
        mt_status = "Failed to connect ❌"
    # 2. Check Telegram
    tg_bot = "Unknown"
    tg_webhook = "Unknown"
    try:
        me = bot.get_me()
        tg_bot = f"@{me.username} ✅"
        wh = bot.get_webhook_info()
        if wh.url:
            tg_webhook = f"Active ({wh.url}) ✅"
            if wh.pending_update_count > 0:
                tg_webhook += f" [Pending updates: {wh.pending_update_count}]"
            if wh.last_error_message:
                tg_webhook += f" | Last Error: {wh.last_error_message}"
        else:
            tg_webhook = "Not Set ❌"
    except Exception as e:
        tg_bot = f"Error: {e} ❌"
    # 3. Check Supabase
    db_status = "Unknown"
    try:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        res = requests.get(f"{SUPABASE_URL}/rest/v1/users?select=username&limit=1", headers=headers, timeout=5)
        res.raise_for_status()
        db_status = f"Connected ✅"
    except Exception as e:
        db_status = f"Error: {e} ❌"
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>System Status Dashboard</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; background: #f4f4f9; }}
            .card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); max-width: 600px; margin: 0 auto; }}
            h1 {{ color: #333; }}
            .status-item {{ margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid #eee; }}
            .label {{ font-weight: bold; color: #555; }}
            .value {{ margin-top: 5px; color: #111; word-wrap: break-word; }}
            .setup-btn {{ display: inline-block; margin-top: 20px; padding: 10px 15px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>📊 System Status Dashboard</h1>
            <div class="status-item">
                <div class="label">🌐 Vercel Host:</div>
                <div class="value">{request.host}</div>
            </div>
            <div class="status-item">
                <div class="label">🤖 Telegram Bot:</div>
                <div class="value">{tg_bot}</div>
            </div>
            <div class="status-item">
                <div class="label">🔗 Telegram Webhook:</div>
                <div class="value">{tg_webhook}</div>
            </div>
            <div class="status-item">
                <div class="label">📡 MikroTik Router:</div>
                <div class="value">{mt_status} (Uptime: {mt_uptime})</div>
            </div>
            <div class="status-item">
                <div class="label">🗄️ Supabase Database:</div>
                <div class="value">{db_status}</div>
            </div>
            <div class="status-item">
                <div class="label">Admin Chat ID Configured:</div>
                <div class="value">{TELEGRAM_CHAT_ID}</div>
            </div>
            <a href="/api/setup" class="setup-btn">🔄 Re-register Webhook</a>
        </div>
    </body>
    </html>
    """
    return html
@app.route('/api/cron/check-expiration', methods=['GET', 'POST'])
@require_cron_auth
def cron_check_expiration():
    logger.info("Running expiration checker...")
    errors = []

    try:
        res = supabase.table('users').select('*').execute()
    except Exception as e:
        logger.error(f"Cron: DB fetch failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

    users = res.data or []
    users_to_delete = []

    for user_data in users:
        username = user_data["username"]
        try:
            if user_data["approved"] and user_data["expiration_timestamp"]:
                expiration_time = parse_isoformat(user_data["expiration_timestamp"])
                if expiration_time and datetime.datetime.now(datetime.timezone.utc) > expiration_time:
                    logger.info(f"User {username} has expired.")
                    if mikrotik.delete_hotspot_user(username):
                        users_to_delete.append(username)
                        bot.send_message(TELEGRAM_CHAT_ID, f"User {username} has expired and been removed from MikroTik.")
                    else:
                        errors.append(f"MikroTik delete failed for {username}")
                        logger.error(f"Failed to delete expired user {username} from MikroTik.")
            elif not user_data["approved"]:
                registration_time = parse_isoformat(user_data["registration_timestamp"])
                if registration_time and datetime.datetime.now(datetime.timezone.utc) - registration_time > datetime.timedelta(hours=24):
                    logger.info(f"Unapproved user {username} older than 24h, removing.")
                    users_to_delete.append(username)
                    bot.send_message(TELEGRAM_CHAT_ID, f"Unapproved user {username} removed after 24 hours.")
        except Exception as e:
            errors.append(f"{username}: {e}")
            logger.error(f"Cron error processing user {username}: {e}", exc_info=True)
            continue  # Don't let one bad row kill the whole loop

    for username in users_to_delete:
        try:
            res_user = supabase.table('users').select('screenshot_url').eq('username', username).execute()
            if res_user.data:
                try:
                    screenshot_filename = res_user.data[0]["screenshot_url"].split('/')[-1]
                    supabase.storage.from_('screenshots').remove([screenshot_filename])
                except Exception as e:
                    logger.warning(f"Screenshot cleanup failed for {username}: {e}")
            supabase.table('users').delete().eq('username', username).execute()
        except Exception as e:
            errors.append(f"Cleanup {username}: {e}")
            logger.error(f"Cron cleanup error for {username}: {e}")

    status = "ok" if not errors else "partial"
    return jsonify({"status": status, "deleted": len(users_to_delete), "errors": errors}), 200

# --- Setup Webhook Endpoint ---
@app.route('/api/setup', methods=['GET'])
def setup_webhook():
    webhook_url = f"https://{request.host}/api/webhook"
    try:
        success = bot.set_webhook(url=webhook_url)
        if success:
            return f"Webhook successfully configured to {webhook_url}", 200
        else:
            return "Failed to set webhook with Telegram.", 500
    except Exception as e:
        logger.error(f"Webhook setup failed: {e}")
        return f"Webhook setup error: {e}", 500

# --- Local Development Fallback ---
if __name__ == '__main__':
    app.run(port=5000, debug=True)
