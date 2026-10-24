import time
import secrets
import string
import datetime
from flask import Blueprint, request, redirect, render_template, url_for, jsonify

from backend.config.settings import (
    APP_URL, TELEGRAM_CHAT_ID, logger
)
from backend.database import db
from backend.mikrotik import mikrotik
from backend.bot import bot, notify_admin_error
from backend.payment.uddoktapay import uddoktapay, PACKAGES
from backend.security import (
    sanitize_username, generate_download_token, check_rate_limit
)

payment_bp = Blueprint('payment', __name__)

@payment_bp.route('/payment/checkout', methods=['POST'])
def checkout():
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    if not check_rate_limit(client_ip, limit=10, window=300):
        return render_template(
            'register.html',
            message="Too many requests. Please wait a few minutes.",
            message_type="error"
        ), 429

    phone = request.form.get('phone', '').strip()
    package_id = request.form.get('package', '').strip()

    if not phone or not package_id:
        return render_template('register.html', message="Phone number and package are required!", message_type="error")

    if not phone.isdigit() or len(phone) < 10:
        return render_template('register.html', message="Invalid phone number format.", message_type="error")

    pkg = PACKAGES.get(package_id)
    if not pkg:
        return render_template('register.html', message="Selected package is invalid.", message_type="error")

    # Generate unique username
    base_username = phone
    username = base_username
    suffix = 0
    try:
        while True:
            existing = db.get_user_by_username(username)
            if not existing:
                break
            suffix += 1
            username = f"{base_username}_{suffix}"
            if suffix > 100:
                return render_template('register.html', message="Too many accounts for this number.", message_type="error")
    except Exception as e:
        logger.error(f"DB uniqueness check error: {e}")
        return render_template('register.html', message="Database error. Please try again.", message_type="error")

    password = ''.join(secrets.choice(string.digits) for _ in range(6))
    now = datetime.datetime.now(datetime.timezone.utc)

    # Pre-register user in DB (unapproved pending payment)
    user_data = {
        "username": username,
        "phone": phone,
        "package": package_id,
        "password": password,
        "screenshot_url": "paymently_pending",
        "registration_timestamp": now.isoformat(),
        "approved": False,
        "approval_timestamp": None,
        "expiration_timestamp": None,
        "telegram_message_id": None
    }

    try:
        db.insert_user(user_data)
    except Exception as e:
        logger.error(f"Failed to pre-insert user for payment: {e}")
        return render_template('register.html', message="Service temporarily unavailable.", message_type="error")

    base_url = APP_URL or f"https://{request.host}"
    base_url = base_url.rstrip('/')

    metadata = {
        "username": username,
        "phone": phone,
        "package": package_id,
        "password": password
    }

    res = uddoktapay.create_checkout(
        full_name=phone,
        email=f"{phone}@hotspot.local",
        amount=pkg["amount"],
        metadata=metadata,
        redirect_url=f"{base_url}/payment/success",
        cancel_url=f"{base_url}/payment/cancel",
        webhook_url=f"{base_url}/api/payment/webhook"
    )

    if res.get("status") and res.get("payment_url"):
        return redirect(res["payment_url"])

    logger.error(f"UddoktaPay checkout failed: {res.get('message')}")
    # Remove pending record on checkout failure
    db.delete_user(username)
    return render_template(
        'register.html',
        message=f"Payment initialization failed: {res.get('message')}",
        message_type="error"
    )

@payment_bp.route('/api/payment/webhook', methods=['POST'])
def payment_webhook():
    api_key_header = request.headers.get('RT-UDDOKTAPAY-API-KEY', '')
    if not uddoktapay.verify_webhook(api_key_header):
        logger.warning(f"Unauthorized payment webhook attempt from {request.remote_addr}")
        return jsonify({"status": False, "message": "Unauthorized"}), 401

    data = request.get_json(silent=True) or request.form.to_dict()
    if not data:
        return jsonify({"status": False, "message": "No data received"}), 400

    invoice_id = data.get('invoice_id')
    status = data.get('status')
    metadata = data.get('metadata') or {}
    trx_id = data.get('transaction_id', 'N/A')
    method = data.get('payment_method', 'N/A')
    amount = data.get('amount', '0')

    logger.info(f"Received UddoktaPay webhook: invoice={invoice_id}, status={status}, method={method}")

    if str(status).upper() != "COMPLETED":
        return jsonify({"status": True, "message": "Ignored non-completed status"}), 200

    username = metadata.get('username')
    password = metadata.get('password')
    package_id = metadata.get('package')
    phone = metadata.get('phone')

    # If metadata was not passed back directly, look up user by username
    if not username:
        logger.error("Webhook payload missing username in metadata")
        return jsonify({"status": False, "message": "Missing metadata"}), 400

    user_data = db.get_user_by_username(username)
    if not user_data:
        logger.error(f"User {username} not found in database for webhook")
        return jsonify({"status": False, "message": "User not found"}), 404

    # Idempotency check: don't re-activate if already approved
    if user_data.get("approved"):
        logger.info(f"User {username} is already activated. Acknowledging webhook.")
        return jsonify({"status": True, "message": "Already processed"}), 200

    pkg = PACKAGES.get(package_id or user_data.get("package"), PACKAGES["15_days_40_tk"])
    expiration_days = pkg["days"]

    approval_time = datetime.datetime.now(datetime.timezone.utc)
    expiration_time = approval_time + datetime.timedelta(days=expiration_days)

    # 1. Activate on MikroTik Router immediately
    mt_created = mikrotik.add_hotspot_user(username, password or user_data["password"], package_id)
    mt_enabled = mikrotik.enable_hotspot_user(username)

    if not (mt_created and mt_enabled):
        logger.error(f"Failed to create/enable user {username} on MikroTik upon payment")
        notify_admin_error("uddoktapay/mikrotik", f"Payment completed for {username} but MikroTik activation failed!")

    # 2. Update Database Record
    db.update_user(username, {
        "approved": True,
        "approval_timestamp": approval_time.isoformat(),
        "expiration_timestamp": expiration_time.isoformat(),
        "screenshot_url": f"paymently:{trx_id}"
    })

    # 3. Notify Admin via Telegram
    if TELEGRAM_CHAT_ID:
        text = (
            f"💰 **Automated Payment Received!**\n\n"
            f"👤 **User:** `{username}`\n"
            f"📞 **Phone:** `{phone or user_data.get('phone')}`\n"
            f"💵 **Amount:** `{amount} BDT` ({method.upper()})\n"
            f"🆔 **TrxID:** `{trx_id}`\n"
            f"📦 **Package:** `{pkg['name']}`\n"
            f"⏳ **Expires:** `{expiration_time.strftime('%Y-%m-%d')}`\n\n"
            f"✅ **Account automatically created & activated on router!**"
        )
        try:
            bot.send_message(TELEGRAM_CHAT_ID, text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Telegram notification failed for payment {username}: {e}")

    return jsonify({"status": True, "message": "User activated successfully"}), 200

@payment_bp.route('/payment/success', methods=['GET'])
def payment_success():
    invoice_id = request.args.get('invoice_id')
    if not invoice_id:
        return redirect(url_for('web.register'))

    # Verify payment status with gateway
    verify_data = uddoktapay.verify_payment(invoice_id)
    if not verify_data or str(verify_data.get('status')).upper() != "COMPLETED":
        return render_template(
            'register.html',
            message="Payment verification pending or failed. Please check with admin if amount was deducted.",
            message_type="error"
        )

    metadata = verify_data.get('metadata') or {}
    username = metadata.get('username')
    if not username:
        return redirect(url_for('web.register'))

    user_data = db.get_user_by_username(username)
    if not user_data:
        return "User account processing. Please refresh in a moment.", 200

    token = generate_download_token(username, user_data['password'])
    download_link = url_for('web.download_credentials', username=username, token=token)

    return render_template(
        'success.html',
        username=username,
        password=user_data['password'],
        download_link=download_link,
        auto_approved=True
    )

@payment_bp.route('/payment/cancel', methods=['GET'])
def payment_cancel():
    return render_template(
        'register.html',
        message="Payment was cancelled. You can select your package and try again.",
        message_type="error"
    )
