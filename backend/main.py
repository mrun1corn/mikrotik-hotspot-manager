import os
import json
import time
import threading
import datetime
import random
import string
from flask import Flask, request, render_template, send_file, redirect, url_for
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from telebot import TeleBot, types
from routeros_api import RouterOsApiPool

# Load environment variables from .env file
load_dotenv()

MIKROTIK_IP = os.getenv('MIKROTIK_IP')
MIKROTIK_USER = os.getenv('MIKROTIK_USER')
MIKROTIK_PASS = os.getenv('MIKROTIK_PASS')
MIKROTIK_API_PORT = int(os.getenv('MIKROTIK_API_PORT'))
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = int(os.getenv('TELEGRAM_CHAT_ID'))
SERVER_IP = os.getenv('SERVER_IP')

app = Flask(__name__, template_folder='templates')
bot = TeleBot(TELEGRAM_BOT_TOKEN)

USERS_FILE = 'users.json'
UPLOAD_FOLDER = 'uploads'
CREDENTIALS_FOLDER = 'credentials'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CREDENTIALS_FOLDER, exist_ok=True)

# --- MikroTik API Interaction ---
class MikroTikAPI:
    def __init__(self, ip, user, password, port):
        self.ip = ip
        self.user = user
        self.password = password
        self.port = port
        self.pool = None
        self.api = None

    def connect(self):
        """Establishes the connection pool to MikroTik."""
        try:
            self.pool = RouterOsApiPool(
                self.ip,
                username=self.user,
                password=self.password,
                port=self.port,
                plaintext_login=True
            )
            self.api = self.pool.get_api()
            print("MikroTik Connection Pool established.")
            return True
        except Exception as e:
            print(f"Error establishing MikroTik Connection Pool: {e}")
            self.pool = None
            self.api = None
            return False

    def disconnect(self):
        """Closes the MikroTik connection pool."""
        if self.pool:
            self.pool.disconnect()
            print("Disconnected from MikroTik API.")
        self.pool = None
        self.api = None

    def add_hotspot_user(self, username, password):
        """Adds a hotspot user with the default profile."""
        if not self.api:
            if not self.connect():
                print("Cannot add user: MikroTik API connection not available.")
                return False
        try:
            users = self.api.get_resource('/ip/hotspot/user')
            users.add(
                name=username,
                password=password,
                profile='default',
                disabled='yes'
            )
            print(f"MikroTik user '{username}' added (disabled) with default profile.")
            return True
        except Exception as e:
            print(f"Error adding MikroTik user '{username}': {e}")
            return False

    def enable_hotspot_user(self, username):
        """Enables a hotspot user in MikroTik."""
        if not self.api:
            if not self.connect():
                print("Cannot enable user: MikroTik API connection not available.")
                return False
        try:
            users = self.api.get_resource('/ip/hotspot/user')
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

    def delete_hotspot_user(self, username):
        """Deletes a hotspot user from MikroTik."""
        if not self.api:
            if not self.connect():
                print("Cannot delete user: MikroTik API connection not available.")
                return False
        try:
            users = self.api.get_resource('/ip/hotspot/user')
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

mikrotik = MikroTikAPI(MIKROTIK_IP, MIKROTIK_USER, MIKROTIK_PASS, MIKROTIK_API_PORT)

# --- User Data Management ---
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)

# --- Flask Web Server ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        phone = request.form['phone']
        package = request.form['package']
        screenshot = request.files['screenshot']

        if not phone or not package or not screenshot:
            return render_template('register.html', message="All fields are required!", message_type="error")

        # Validate phone number (simple check)
        if not phone.isdigit() or len(phone) < 10:
            return render_template('register.html', message="Invalid phone number.", message_type="error")

        # Generate username (phone number, ensure uniqueness)
        base_username = phone
        username = base_username
        users = load_users()
        suffix = 0
        while username in users:
            suffix += 1
            username = f"{base_username}_{suffix}"

        # Generate 6-digit numeric password
        password = ''.join(random.choices(string.digits, k=6))

        # Save screenshot
        screenshot_filename = f"{username}_{int(time.time())}_{screenshot.filename}"
        screenshot_path = os.path.join(UPLOAD_FOLDER, screenshot_filename)
        screenshot.save(screenshot_path)

        # Determine expiration based on package
        expiration_days = 0
        if package == "15_days_40_tk":
            expiration_days = 15
        elif package == "30_days_100_tk":
            expiration_days = 30
        else:
            return render_template('register.html', message="Invalid package selected.", message_type="error")

        # Store user info in JSON
        users[username] = {
            "phone": phone,
            "package": package,
            "password": password,
            "screenshot_path": screenshot_path,
            "registration_timestamp": datetime.datetime.now().isoformat(),
            "approved": False,
            "approval_timestamp": None,
            "expiration_timestamp": None,
            "telegram_message_id": None
        }
        save_users(users)

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
            with open(screenshot_path, 'rb') as photo:
                message = bot.send_photo(TELEGRAM_CHAT_ID, photo, caption=caption, reply_markup=keyboard)
                users[username]["telegram_message_id"] = message.message_id
                save_users(users)
        except Exception as e:
            print(f"Error sending Telegram notification: {e}")
            # Consider logging this error and potentially retrying or notifying admin via other means

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
    users = load_users()
    user_data = users.get(username)

    if not user_data:
        return "User not found", 404

    username_text = f"Username: {username}"
    password_text = f"Password: {user_data['password']}"

    # Create an image with credentials
    img = Image.new('RGB', (400, 200), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except IOError:
        font = ImageFont.load_default()

    d.text((50, 70), username_text, fill=(0, 0, 0), font=font)
    d.text((50, 110), password_text, fill=(0, 0, 0), font=font)

    credentials_filename = f"{username}_credentials.png"
    credentials_path = os.path.join(CREDENTIALS_FOLDER, credentials_filename)
    img.save(credentials_path)

    return send_file(credentials_path, as_attachment=True)

# --- Telegram Bot ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.id == TELEGRAM_CHAT_ID:
        bot.reply_to(message, "Welcome, admin! I'm ready to manage hotspot users.")
    else:
        bot.reply_to(message, "You are not authorized to use this bot.")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.from_user.id != TELEGRAM_CHAT_ID:
        bot.answer_callback_query(call.id, "You are not authorized to perform this action.")
        return

    action, username = call.data.split('_', 1)
    users = load_users()
    user_data = users.get(username)

    if not user_data:
        bot.answer_callback_query(call.id, "User data not found.")
        return

    if action == "approve":
        if user_data["approved"]:
            bot.answer_callback_query(call.id, "User already approved.")
            return

        # Add and enable user in MikroTik
        if mikrotik.add_hotspot_user(username, user_data["password"]) and \
           mikrotik.enable_hotspot_user(username):
            # Update user data
            user_data["approved"] = True
            user_data["approval_timestamp"] = datetime.datetime.now().isoformat()

            # Calculate expiration timestamp
            expiration_days = 0
            if user_data["package"] == "15_days_40_tk":
                expiration_days = 15
            elif user_data["package"] == "30_days_100_tk":
                expiration_days = 30
            user_data["expiration_timestamp"] = (datetime.datetime.now() + datetime.timedelta(days=expiration_days)).isoformat()

            save_users(users)
            bot.answer_callback_query(call.id, f"User {username} approved and enabled.")
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=call.message.caption + "\n\n✅ Approved!",
                reply_markup=None
            )
            bot.send_message(TELEGRAM_CHAT_ID, f"User {username} has been approved and enabled in MikroTik. Expires on {user_data['expiration_timestamp'].split('T')[0]}.")
        else:
            bot.answer_callback_query(call.id, f"Failed to add/enable user {username} in MikroTik.")

    elif action == "reject":
        if user_data["approved"]:
            bot.answer_callback_query(call.id, "Cannot reject an already approved user.")
            return

        # Remove user from users.json
        del users[username]
        save_users(users)
        bot.answer_callback_query(call.id, f"User {username} rejected and removed.")
        bot.edit_message_caption(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            caption=call.message.caption + "\n\n❌ Rejected!",
            reply_markup=None
        )
        bot.send_message(TELEGRAM_CHAT_ID, f"User {username} has been rejected and removed.")

# --- Expiration Handling ---
def expiration_checker():
    while True:
        print("Running expiration checker...")
        users = load_users()
        users_to_delete = []

        for username, user_data in users.items():
            if user_data["approved"] and user_data["expiration_timestamp"]:
                expiration_time = datetime.datetime.fromisoformat(user_data["expiration_timestamp"])
                if datetime.datetime.now() > expiration_time:
                    print(f"User {username} has expired. Deleting from MikroTik and users.json.")
                    if mikrotik.delete_hotspot_user(username):
                        users_to_delete.append(username)
                        bot.send_message(TELEGRAM_CHAT_ID, f"User {username} has expired and been removed from MikroTik.")
                    else:
                        print(f"Failed to delete expired user {username} from MikroTik.")
            elif not user_data["approved"]:
                # Clean up unapproved users older than 24 hours
                registration_time = datetime.datetime.fromisoformat(user_data["registration_timestamp"])
                if datetime.datetime.now() - registration_time > datetime.timedelta(hours=24):
                    print(f"User {username} was never approved and is older than 24 hours. Removing from JSON.")
                    users_to_delete.append(username)
                    bot.send_message(TELEGRAM_CHAT_ID, f"Unapproved user {username} removed after 24 hours.")

        for username in users_to_delete:
            if username in users:
                del users[username]
        save_users(users)
        time.sleep(600)  # Run every 10 minutes

# --- Main Execution ---
if __name__ == '__main__':
    # Start MikroTik connection pool
    mikrotik.connect()

    # Start expiration checker in a separate thread
    expiration_thread = threading.Thread(target=expiration_checker)
    expiration_thread.daemon = True
    expiration_thread.start()

    # Start Telegram bot polling in a separate thread
    telegram_thread = threading.Thread(target=bot.polling, kwargs={'none_stop': True})
    telegram_thread.daemon = True
    telegram_thread.start()

    # Start Flask app
    print(f"Flask app running on http://{SERVER_IP}:5000")
    app.run(host=SERVER_IP, port=5000)