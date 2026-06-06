import os
import time
import datetime
import random
import string
import secrets
import io
from flask import Flask, request, render_template, send_file, url_for
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

app = Flask(__name__, template_folder='templates')
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
            print(f"Error establishing MikroTik Connection: {e}")
            return None

    def add_hotspot_user(self, username, password, package):
        """Adds a hotspot user with the package-specific profile."""
        pool = self.connect()
        if not pool:
            print("Cannot add user: MikroTik API connection not available.")
            return False
        try:
            api = pool.get_api()
            users = api.get_resource('/ip/hotspot/user')
            
            # Map package selection to MikroTik profile name
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
            print(f"MikroTik user '{username}' added (disabled) with profile '{profile_name}'.")
            return True
        except Exception as e:
            print(f"Error adding MikroTik user '{username}': {e}")
            return False
        finally:
            pool.disconnect()

    def enable_hotspot_user(self, username):
        """Enables a hotspot user in MikroTik."""
        pool = self.connect()
        if not pool:
            print("Cannot enable user: MikroTik API connection not available.")
            return False
        try:
            api = pool.get_api()
            users = api.get_resource('/ip/hotspot/user')
            user = users.get(name=username)
            if user:
                users.set(id=user[0]['id'], disabled='no')
                print(f"MikroTik user '{username}' enabled.")
                return True
            else:
                print(f"MikroTik user '{username}' not found for enabling.")
                return False
        except Exception as e:
            print(f"Error enabling MikroTik user '{username}': {e}")
            return False
        finally:
            pool.disconnect()

    def delete_hotspot_user(self, username):
        """Deletes a hotspot user from MikroTik."""
        pool = self.connect()
        if not pool:
            print("Cannot delete user: MikroTik API connection not available.")
            return False
        try:
            api = pool.get_api()
            users = api.get_resource('/ip/hotspot/user')
            user = users.get(name=username)
            if user:
                users.remove(id=user[0]['id'])
                print(f"MikroTik user '{username}' deleted.")
                return True
            else:
                print(f"MikroTik user '{username}' not found for deletion.")
                return False
        except Exception as e:
            print(f"Error deleting MikroTik user '{username}': {e}")
            return False
        finally:
            pool.disconnect()

mikrotik = MikroTikAPI(MIKROTIK_IP, MIKROTIK_USER, MIKROTIK_PASS, MIKROTIK_API_PORT)

# --- Flask Web Server ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        phone = request.form.get('phone')
        package = request.form.get('package')
        screenshot = request.files.get('screenshot')

        if not phone or not package or not screenshot:
            return render_template('register.html', message="All fields are required!", message_type="error")

        # Validate phone number
        if not phone.isdigit() or len(phone) < 10:
            return render_template('register.html', message="Invalid phone number.", message_type="error")

        # Generate unique username
        base_username = phone
        username = base_username
        suffix = 0
        while True:
            res = supabase.table('users').select('username').eq('username', username).execute()
            if not res.data:
                break
            suffix += 1
            username = f"{base_username}_{suffix}"

        # Generate cryptographically secure 6-digit numeric password
        password = ''.join(secrets.choice(string.digits) for _ in range(6))

        # Upload screenshot to Supabase Storage
        screenshot_filename = f"{username}_{int(time.time())}_{screenshot.filename}"
        screenshot_bytes = screenshot.read()
        try:
            supabase.storage.from_('screenshots').upload(
                path=screenshot_filename,
                file=screenshot_bytes,
                file_options={"content-type": screenshot.content_type}
            )
            screenshot_url = supabase.storage.from_('screenshots').get_public_url(screenshot_filename)
        except Exception as e:
            print(f"Error uploading screenshot to Supabase: {e}")
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
            print(f"Error saving user to Supabase: {e}")
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
            print(f"Error sending Telegram notification: {e}")

        # Redirect to success page
        return render_template(
            'success.html',
            username=username,
            password=password,
            download_link=url_for('download_credentials', username=username)
        )
    return render_template('register.html')

@app.route('/download/<username>')
def download_credentials(username):
    # Retrieve user from Supabase to prevent unauthenticated leakage of random user info
    # (Checking a session/cookie would be better, but verifying user exists is a baseline check)
    res = supabase.table('users').select('*').eq('username', username).execute()
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
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        return 'Forbidden', 403

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.id == TELEGRAM_CHAT_ID:
        bot.reply_to(message, "Welcome, admin! I'm ready to manage hotspot users via webhooks.")
    else:
        bot.reply_to(message, "You are not authorized to use this bot.")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.from_user.id != TELEGRAM_CHAT_ID:
        bot.answer_callback_query(call.id, "You are not authorized to perform this action.")
        return

    action, username = call.data.split('_', 1)
    
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
            
            # Calculate expiration
            expiration_days = 15 if user_data["package"] == "15_days_40_tk" else 30
            approval_time = datetime.datetime.now(datetime.timezone.utc)
            expiration_time = approval_time + datetime.timedelta(days=expiration_days)

            # Update DB
            supabase.table('users').update({
                "approved": True,
                "approval_timestamp": approval_time.isoformat(),
                "expiration_timestamp": expiration_time.isoformat()
            }).eq("username", username).execute()

            bot.answer_callback_query(call.id, f"User {username} approved and enabled.")
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=call.message.caption + "\n\n✅ Approved!",
                reply_markup=None
            )
            bot.send_message(TELEGRAM_CHAT_ID, f"User {username} has been approved and enabled in MikroTik. Expires on {expiration_time.strftime('%Y-%m-%d')}.")
        else:
            bot.answer_callback_query(call.id, f"Failed to add/enable user {username} in MikroTik.")

    elif action == "reject":
        if user_data["approved"]:
            bot.answer_callback_query(call.id, "Cannot reject an already approved user.")
            return

        # Delete screenshot from Supabase storage
        try:
            screenshot_filename = user_data["screenshot_url"].split('/')[-1]
            supabase.storage.from_('screenshots').remove([screenshot_filename])
        except Exception as e:
            print(f"Error removing screenshot from Supabase Storage: {e}")

        # Remove user from Supabase DB
        supabase.table('users').delete().eq("username", username).execute()

        bot.answer_callback_query(call.id, f"User {username} rejected and removed.")
        bot.edit_message_caption(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            caption=call.message.caption + "\n\n❌ Rejected!",
            reply_markup=None
        )
        bot.send_message(TELEGRAM_CHAT_ID, f"User {username} has been rejected and removed.")

# --- Cron Job Expiration Checker Route ---
@app.route('/api/cron/check-expiration', methods=['GET', 'POST'])
def cron_check_expiration():
    print("Running expiration checker...")
    
    res = supabase.table('users').select('*').execute()
    users = res.data or []
    users_to_delete = []

    for user_data in users:
        username = user_data["username"]
        if user_data["approved"] and user_data["expiration_timestamp"]:
            expiration_time = parse_isoformat(user_data["expiration_timestamp"])
            if datetime.datetime.now(datetime.timezone.utc) > expiration_time:
                print(f"User {username} has expired. Deleting from MikroTik and Supabase.")
                if mikrotik.delete_hotspot_user(username):
                    users_to_delete.append(username)
                    bot.send_message(TELEGRAM_CHAT_ID, f"User {username} has expired and been removed from MikroTik.")
                else:
                    print(f"Failed to delete expired user {username} from MikroTik.")
        elif not user_data["approved"]:
            # Clean up unapproved users older than 24 hours
            registration_time = parse_isoformat(user_data["registration_timestamp"])
            if datetime.datetime.now(datetime.timezone.utc) - registration_time > datetime.timedelta(hours=24):
                print(f"User {username} was never approved and is older than 24 hours. Removing.")
                users_to_delete.append(username)
                bot.send_message(TELEGRAM_CHAT_ID, f"Unapproved user {username} removed after 24 hours.")

    for username in users_to_delete:
        # Delete screenshot
        res_user = supabase.table('users').select('screenshot_url').eq('username', username).execute()
        if res_user.data:
            try:
                screenshot_filename = res_user.data[0]["screenshot_url"].split('/')[-1]
                supabase.storage.from_('screenshots').remove([screenshot_filename])
            except Exception as e:
                print(f"Error removing screenshot for {username}: {e}")

        # Delete database row
        supabase.table('users').delete().eq('username', username).execute()

    return 'OK', 200

# --- Setup Webhook Endpoint ---
@app.route('/api/setup', methods=['GET'])
def setup_webhook():
    webhook_url = f"https://{request.host}/api/webhook"
    success = bot.set_webhook(url=webhook_url)
    if success:
        return f"Webhook successfully configured to {webhook_url}", 200
    else:
        return "Failed to set webhook with Telegram.", 500

# --- Local Development Fallback ---
if __name__ == '__main__':
    # Local run (for testing)
    app.run(port=5000, debug=True)
