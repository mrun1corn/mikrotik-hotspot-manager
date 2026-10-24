import re
import io
import time
import hmac
import hashlib
import datetime
from functools import wraps
from flask import request
from PIL import Image

try:
    from backend.config import CRON_SECRET, SECRET_KEY, logger
except ImportError:
    from config import CRON_SECRET, SECRET_KEY, logger

# In-memory IP rate limiter: {ip: [timestamps]}
_rate_limits = {}

def sanitize_username(username):
    """Only allow alphanumeric, underscore, and dash."""
    if not username:
        return ""
    return re.sub(r'[^a-zA-Z0-9_\-]', '', str(username))

def parse_isoformat(dt_str):
    """Safely parse ISO datetime string."""
    if not dt_str:
        return None
    if dt_str.endswith('Z'):
        dt_str = dt_str[:-1] + '+00:00'
    return datetime.datetime.fromisoformat(dt_str)

def generate_download_token(username, password):
    """Generate an HMAC-SHA256 signature for credential downloads."""
    data = f"{username}:{password}:{SECRET_KEY}"
    return hmac.new(SECRET_KEY.encode('utf-8'), data.encode('utf-8'), hashlib.sha256).hexdigest()[:24]

def verify_download_token(username, password, token):
    """Validate the provided download token using constant-time comparison."""
    if not token or not username or not password:
        return False
    expected = generate_download_token(username, password)
    return hmac.compare_digest(str(token), str(expected))

def verify_image_file(file_bytes):
    """Deeply inspect image file bytes with Pillow to prevent arbitrary file upload."""
    if not file_bytes or len(file_bytes) > 5 * 1024 * 1024:
        return False, "Image must be under 5MB."
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()
        if img.format.lower() not in ('jpeg', 'jpg', 'png', 'webp', 'gif'):
            return False, "Unsupported image format. Allowed: JPG, PNG, WebP."
        return True, ""
    except Exception as e:
        logger.warning(f"Image verification failed: {e}")
        return False, "Corrupted or invalid image file."

def check_rate_limit(ip, limit=5, window=300):
    """In-memory rate limiter per IP. Returns True if request is allowed."""
    now = time.time()
    # Filter out timestamps outside window
    timestamps = [t for t in _rate_limits.get(ip, []) if now - t < window]
    if len(timestamps) >= limit:
        return False
    timestamps.append(now)
    _rate_limits[ip] = timestamps
    return True

def require_cron_auth(f):
    """Protect cron endpoints from unauthorized execution."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        cron_header = request.headers.get('x-vercel-cron', '')
        # Direct Vercel Cron invocation
        if cron_header:
            return f(*args, **kwargs)
        # Bearer token invocation
        expected_secret = CRON_SECRET or SECRET_KEY
        if expected_secret and auth == f'Bearer {expected_secret}':
            return f(*args, **kwargs)
        logger.warning(f"Unauthorized cron attempt from {request.remote_addr}")
        return 'Unauthorized', 401
    return decorated

def require_admin_auth(f):
    """Protect internal endpoints (e.g. /status, /api/setup)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        key_param = request.args.get('key') or request.args.get('secret', '')
        expected_secret = CRON_SECRET or SECRET_KEY
        if expected_secret and (auth == f'Bearer {expected_secret}' or key_param == expected_secret):
            return f(*args, **kwargs)
        logger.warning(f"Unauthorized admin attempt from {request.remote_addr}")
        return 'Unauthorized: Valid admin secret required (?secret=...)', 401
    return decorated
