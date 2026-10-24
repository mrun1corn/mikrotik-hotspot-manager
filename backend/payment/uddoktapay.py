import requests
import hmac
from backend.config.settings import UDDOKTAPAY_API_KEY, UDDOKTAPAY_API_URL, logger

PACKAGES = {
    "15_days_40_tk": {
        "name": "15 Days - 40 TK",
        "amount": 40,
        "days": 15,
        "profile": "15-days-40TK"
    },
    "30_days_100_tk": {
        "name": "30 Days - 100 TK",
        "amount": 100,
        "days": 30,
        "profile": "30-days-100TK"
    }
}

class UddoktaPayClient:
    def __init__(self, api_key=None, api_url=None):
        self.api_key = api_key or UDDOKTAPAY_API_KEY
        self.api_url = (api_url or UDDOKTAPAY_API_URL or '').rstrip('/')

    def is_configured(self):
        return bool(self.api_key and self.api_url)

    def create_checkout(self, full_name, email, amount, metadata, redirect_url, cancel_url, webhook_url):
        """Initiates a checkout-v2 session on UddoktaPay / Paymently."""
        if not self.is_configured():
            logger.error("UddoktaPay API credentials are not configured")
            return {"status": False, "message": "Payment gateway credentials not configured"}

        endpoint = f"{self.api_url}/checkout-v2"
        headers = {
            "RT-UDDOKTAPAY-API-KEY": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        payload = {
            "full_name": full_name,
            "email": email or f"{full_name}@hotspot.local",
            "amount": str(amount),
            "metadata": metadata,
            "redirect_url": redirect_url,
            "return_type": "GET",
            "cancel_url": cancel_url,
            "webhook_url": webhook_url
        }

        try:
            res = requests.post(endpoint, json=payload, headers=headers, timeout=12)
            data = res.json()
            if res.status_code == 200 and data.get("status"):
                return {
                    "status": True,
                    "payment_url": data.get("payment_url"),
                    "invoice_id": data.get("invoice_id"),
                    "message": data.get("message", "Success")
                }
            logger.error(f"UddoktaPay checkout error: HTTP {res.status_code} - {res.text}")
            return {"status": False, "message": data.get("message", "Failed to initialize payment")}
        except Exception as e:
            logger.error(f"UddoktaPay request failed: {e}")
            return {"status": False, "message": str(e)}

    def verify_payment(self, invoice_id):
        """Verifies payment status via UddoktaPay /api/verify-payment."""
        if not self.is_configured() or not invoice_id:
            return None

        endpoint = f"{self.api_url}/verify-payment"
        headers = {
            "RT-UDDOKTAPAY-API-KEY": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        payload = {"invoice_id": invoice_id}

        try:
            res = requests.post(endpoint, json=payload, headers=headers, timeout=12)
            if res.status_code == 200:
                return res.json()
            logger.error(f"UddoktaPay verify error: HTTP {res.status_code} - {res.text}")
            return None
        except Exception as e:
            logger.error(f"UddoktaPay verify request failed: {e}")
            return None

    def verify_webhook(self, received_api_key):
        """Verifies that the webhook request came genuinely from UddoktaPay."""
        if not self.api_key or not received_api_key:
            return False
        return hmac.compare_digest(str(received_api_key).strip(), str(self.api_key).strip())

uddoktapay = UddoktaPayClient()
