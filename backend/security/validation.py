import re
import io
import time
import datetime
from PIL import Image
from backend.config.settings import logger

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
    timestamps = [t for t in _rate_limits.get(ip, []) if now - t < window]
    if len(timestamps) >= limit:
        return False
    timestamps.append(now)
    _rate_limits[ip] = timestamps
    return True
