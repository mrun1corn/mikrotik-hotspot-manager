import hmac
import hashlib
from backend.config.settings import SECRET_KEY

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
