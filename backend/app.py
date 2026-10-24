from flask import Flask, render_template

try:
    from backend.config import TEMPLATES_DIR, logger
    from backend.routes.web import web_bp
    from backend.routes.webhook import webhook_bp
    from backend.routes.cron import cron_bp
    from backend.routes.payment import payment_bp
except ImportError:
    from config import TEMPLATES_DIR, logger
    from routes.web import web_bp
    from routes.webhook import webhook_bp
    from routes.cron import cron_bp
    from routes.payment import payment_bp

def create_app():
    """Application factory for Flask with Vercel serverless compatibility."""
    app = Flask(__name__, template_folder=TEMPLATES_DIR)

    # --- Register Blueprints ---
    app.register_blueprint(web_bp)
    app.register_blueprint(webhook_bp)
    app.register_blueprint(cron_bp)
    app.register_blueprint(payment_bp)

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

    return app
