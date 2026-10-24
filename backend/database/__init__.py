from backend.database.client import supabase
from backend.database.users import UserManager
from backend.database.storage import StorageManager

# Convenience aliases matching original API
class DatabaseProxy:
    get_user_by_username = staticmethod(UserManager.get_by_username)
    get_all_users = staticmethod(UserManager.get_all)
    insert_user = staticmethod(UserManager.insert)
    update_user = staticmethod(UserManager.update)
    delete_user = staticmethod(UserManager.delete)
    upload_screenshot = staticmethod(StorageManager.upload_screenshot)
    delete_screenshot = staticmethod(StorageManager.delete_screenshot)

db = DatabaseProxy()
