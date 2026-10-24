from routeros_api import RouterOsApiPool

try:
    from backend.config import (
        MIKROTIK_IP, MIKROTIK_USER, MIKROTIK_PASS,
        MIKROTIK_API_PORT, MIKROTIK_USE_SSL, logger
    )
except ImportError:
    from config import (
        MIKROTIK_IP, MIKROTIK_USER, MIKROTIK_PASS,
        MIKROTIK_API_PORT, MIKROTIK_USE_SSL, logger
    )

class MikroTikAPI:
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

    def add_hotspot_user(self, username, password, package):
        """Adds a hotspot user with the package-specific profile."""
        pool = self.connect()
        if not pool:
            return False
        try:
            api = pool.get_api()
            users = api.get_resource('/ip/hotspot/user')

            profile_name = "default"
            if package == "15_days_40_tk":
                profile_name = "15-days-40TK"
            elif package == "30_days_100_tk":
                profile_name = "30-days-100TK"

            users.add(
                name=username,
                password=password,
                profile=profile_name,
                disabled='yes'
            )
            logger.info(f"MikroTik user '{username}' added (disabled), profile='{profile_name}'")
            return True
        except Exception as e:
            logger.warning(f"Error adding MikroTik user '{username}': {e}. Attempting auto-sync...")
            self.sync_initial_setup()
            try:
                pool2 = self.connect()
                if pool2:
                    api2 = pool2.get_api()
                    users2 = api2.get_resource('/ip/hotspot/user')
                    users2.add(name=username, password=password, profile=profile_name, disabled='yes')
                    pool2.disconnect()
                    logger.info(f"MikroTik user '{username}' added successfully after auto-sync.")
                    return True
            except Exception as e2:
                logger.error(f"Failed to add user even after auto-sync: {e2}")
                if 'pool2' in locals() and pool2:
                    pool2.disconnect()
            return False
        finally:
            pool.disconnect()

    def enable_hotspot_user(self, username):
        """Enables a hotspot user in MikroTik."""
        pool = self.connect()
        if not pool:
            return False
        try:
            api = pool.get_api()
            users = api.get_resource('/ip/hotspot/user')
            user = users.get(name=username)
            if user:
                users.set(id=user[0]['id'], disabled='no')
                logger.info(f"MikroTik user '{username}' enabled.")
                return True
            else:
                logger.warning(f"MikroTik user '{username}' not found for enabling.")
                return False
        except Exception as e:
            logger.error(f"Error enabling MikroTik user '{username}': {e}")
            return False
        finally:
            pool.disconnect()

    def delete_hotspot_user(self, username):
        """Deletes a hotspot user from MikroTik."""
        pool = self.connect()
        if not pool:
            return False
        try:
            api = pool.get_api()
            users = api.get_resource('/ip/hotspot/user')
            user = users.get(name=username)
            if user:
                users.remove(id=user[0]['id'])
                logger.info(f"MikroTik user '{username}' deleted.")
                return True
            else:
                logger.warning(f"MikroTik user '{username}' not found for deletion.")
                return False
        except Exception as e:
            logger.error(f"Error deleting MikroTik user '{username}': {e}")
            return False
        finally:
            pool.disconnect()

    def kick_user(self, username):
        """Disconnects an active user session."""
        pool = self.connect()
        if not pool:
            return False
        try:
            api = pool.get_api()
            active = api.get_resource('/ip/hotspot/active')
            sessions = active.get(user=username)
            if sessions:
                for session in sessions:
                    active.remove(id=session['id'])
                logger.info(f"Kicked active session for '{username}'.")
                return True
            return False
        except Exception as e:
            logger.error(f"Error kicking user '{username}': {e}")
            return False
        finally:
            pool.disconnect()

    def get_active_users(self):
        """Returns list of currently active hotspot sessions."""
        pool = self.connect()
        if not pool:
            return []
        try:
            api = pool.get_api()
            active = api.get_resource('/ip/hotspot/active')
            return active.get()
        except Exception as e:
            logger.error(f"Error getting active users: {e}")
            return []
        finally:
            pool.disconnect()

    def reboot_router(self):
        """Reboots the MikroTik router."""
        pool = self.connect()
        if not pool:
            return False
        try:
            api = pool.get_api()
            sys = api.get_binary_resource('/system')
            sys.call('reboot')
            return True
        except Exception:
            # Dropped connection on reboot is expected
            return True

    def get_profiles(self):
        """Returns list of hotspot user profiles."""
        pool = self.connect()
        if not pool:
            return []
        try:
            api = pool.get_api()
            return api.get_resource('/ip/hotspot/user/profile').get()
        except Exception as e:
            logger.error(f"Error getting profiles: {e}")
            return []
        finally:
            pool.disconnect()

    def set_profile_limit(self, profile_name, rate_limit):
        """Changes the UL/DL rate limit for a hotspot profile."""
        pool = self.connect()
        if not pool:
            return False
        try:
            api = pool.get_api()
            profiles = api.get_resource('/ip/hotspot/user/profile')
            p = profiles.get(name=profile_name)
            if p:
                profiles.set(id=p[0]['id'], rate_limit=rate_limit)
                return True
            return False
        except Exception as e:
            logger.error(f"Error setting limit for {profile_name}: {e}")
            return False
        finally:
            pool.disconnect()

    def sync_initial_setup(self):
        """Configures a fresh router with necessary profiles and walled-garden."""
        pool = self.connect()
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
            domains = ['mikrotik-hotspot-manager-one.vercel.app', '*.supabase.co', '*.bkash.com', 'bkash.com', '*.pay.bka.sh', 'pay.bka.sh']
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

# Singleton instance
mikrotik = MikroTikAPI()
