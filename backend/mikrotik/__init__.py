from backend.mikrotik.client import MikroTikClient
from backend.mikrotik.users import HotspotUserManager
from backend.mikrotik.profiles import HotspotProfileManager
from backend.mikrotik.system import RouterSystemManager

class MikroTikController:
    def __init__(self, ip=None, user=None, password=None, port=None, use_ssl=None):
        self.client = MikroTikClient(ip, user, password, port, use_ssl)
        self.users = HotspotUserManager(self.client)
        self.profiles = HotspotProfileManager(self.client)
        self.system = RouterSystemManager(self.client)

    # Proxy methods matching original MikroTikAPI interface
    def connect(self):
        return self.client.connect()

    def add_hotspot_user(self, username, password, package):
        return self.users.add_user(username, password, package, sync_callback=self.system.sync_initial_setup)

    def enable_hotspot_user(self, username):
        return self.users.enable_user(username)

    def login_active_host(self, username, password):
        return self.users.login_active_host(username, password)

    def delete_hotspot_user(self, username):
        return self.users.delete_user(username)

    def kick_user(self, username):
        return self.users.kick_user(username)

    def get_active_users(self):
        return self.users.get_active_users()

    def reboot_router(self):
        return self.system.reboot()

    def get_profiles(self):
        return self.profiles.get_profiles()

    def set_profile_limit(self, profile_name, rate_limit):
        return self.profiles.set_profile_limit(profile_name, rate_limit)

    def sync_initial_setup(self):
        return self.system.sync_initial_setup()

    def get_logs(self):
        return self.system.get_logs()

# Singleton controller instance
mikrotik = MikroTikController()
