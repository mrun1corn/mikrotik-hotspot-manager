import os
import sys

# Ensure backend directory is in sys.path for both local development and Vercel serverless runtime
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PARENT_DIR = os.path.abspath(os.path.join(BASE_DIR, '..'))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

try:
    from backend.app import create_app
except ImportError:
    from app import create_app

# WSGI Application instance for Vercel
app = create_app()

if __name__ == '__main__':
    app.run(port=5000, debug=True)
