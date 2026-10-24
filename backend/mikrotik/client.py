from routeros_api import RouterOsApiPool
from backend.config.settings import (
    MIKROTIK_IP, MIKROTIK_USER, MIKROTIK_PASS,
    MIKROTIK_API_PORT, MIKROTIK_USE_SSL, logger
)

class MikroTikClient:
    def __init__(self, ip=None, user=None, password=None, port=None, use_ssl=None):
        self.ip = ip or MIKROTIK_IP
        self.user = user or MIKROTIK_USER
        self.password = password or MIKROTIK_PASS
        self.port = port or MIKROTIK_API_PORT
        self.use_ssl = use_ssl if use_ssl is not None else MIKROTIK_USE_SSL

    def connect(self):
        """Establishes connection to MikroTik router with SSL/TLS encryption support."""
        try:
            pool = RouterOsApiPool(
                self.ip,
                username=self.user,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=False,
                plaintext_login=not self.use_ssl
            )
            return pool
        except Exception as e:
            logger.error(f"MikroTik connection failed to {self.ip}:{self.port} (SSL={self.use_ssl}): {e}")
            return None
