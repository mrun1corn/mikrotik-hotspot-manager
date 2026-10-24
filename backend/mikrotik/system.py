from backend.config.settings import logger

class RouterSystemManager:
    def __init__(self, client):
        self.client = client

    def reboot(self):
        """Reboots the MikroTik router."""
        pool = self.client.connect()
        if not pool:
            return False
        try:
            api = pool.get_api()
            sys = api.get_binary_resource('/system')
            sys.call('reboot')
            return True
        except Exception:
            # Expected connection drop on reboot
            return True

    def get_resource(self):
        """Fetches /system/resource (uptime, cpu, memory, version)."""
        pool = self.client.connect()
        if not pool:
            return None
        try:
            api = pool.get_api()
            res = api.get_resource('/system/resource').get()
            return res[0] if res else None
        except Exception as e:
            logger.error(f"Error getting router resource: {e}")
            return None
        finally:
            pool.disconnect()

    def get_logs(self):
        """Fetches /log entries from router."""
        pool = self.client.connect()
        if not pool:
            return []
        try:
            api = pool.get_api()
            logs = api.get_resource('/log').get()
            return logs or []
        except Exception as e:
            logger.error(f"Error getting router logs: {e}")
            return []
        finally:
            pool.disconnect()

    def sync_initial_setup(self):
        """Configures a fresh router with necessary profiles and walled-garden."""
        pool = self.client.connect()
        if not pool:
            return "Connection failed"
        try:
            api = pool.get_api()
            log = []
            # 1. Profiles
            profiles = api.get_resource('/ip/hotspot/user/profile')
            existing_profiles = [p.get('name') for p in profiles.get()]
            if '15-days-40TK' not in existing_profiles:
                profiles.add(name='15-days-40TK', rate_limit='2M/2M', shared_users='1')
                log.append("Created profile: 15-days-40TK (2M/2M)")
            if '30-days-100TK' not in existing_profiles:
                profiles.add(name='30-days-100TK', rate_limit='5M/5M', shared_users='1')
                log.append("Created profile: 30-days-100TK (5M/5M)")
            # 2. Walled Garden
            wg = api.get_resource('/ip/hotspot/walled-garden')
            existing_wg = [w.get('dst-host') for w in wg.get() if 'dst-host' in w]
            domains = [
                'mikrotik-hotspot-manager-one.vercel.app', '*.supabase.co',
                'rob1n.paymently.io', '*.paymently.io',
                '*.bkash.com', 'bkash.com', '*.pay.bka.sh', 'pay.bka.sh',
                '*.nagad.com.bd', '*.upay.systems', '*.dutchbanglabank.com', '*.sslcommerz.com'
            ]
            for d in domains:
                if d not in existing_wg:
                    wg.add(dst_host=d, action='allow')
                    log.append(f"Added Walled Garden: {d}")
            if not log:
                return "Router is already fully synced! No missing configurations."
            return "\n".join(log)
        except Exception as e:
            logger.error(f"Sync error: {e}")
            return f"Error during sync: {e}"
        finally:
            pool.disconnect()
