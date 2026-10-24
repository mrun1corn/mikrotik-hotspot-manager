from backend.config.settings import logger

class HotspotUserManager:
    def __init__(self, client):
        self.client = client

    def add_user(self, username, password, package, sync_callback=None):
        """Adds a hotspot user with the package-specific profile."""
        pool = self.client.connect()
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
            if sync_callback:
                sync_callback()
            try:
                pool2 = self.client.connect()
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

    def enable_user(self, username):
        """Enables a hotspot user in MikroTik."""
        pool = self.client.connect()
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

    def delete_user(self, username):
        """Deletes a hotspot user from MikroTik."""
        pool = self.client.connect()
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
        pool = self.client.connect()
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
        pool = self.client.connect()
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
