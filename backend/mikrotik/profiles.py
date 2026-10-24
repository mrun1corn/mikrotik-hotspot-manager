from backend.config.settings import logger

class HotspotProfileManager:
    def __init__(self, client):
        self.client = client

    def get_profiles(self):
        """Returns list of hotspot user profiles."""
        pool = self.client.connect()
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
        pool = self.client.connect()
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
