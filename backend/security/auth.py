from functools import wraps
from flask import request
from backend.config.settings import CRON_SECRET, SECRET_KEY, logger

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
