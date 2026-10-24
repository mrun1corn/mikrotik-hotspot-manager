from backend.database.client import supabase
from backend.database.storage import StorageManager
from backend.config.settings import logger

class UserManager:
    @staticmethod
    def get_by_username(username):
        """Fetch a single user row by username."""
        if not supabase:
            return None
        res = supabase.table('users').select('*').eq('username', username).execute()
        return res.data[0] if res.data else None

    @staticmethod
    def get_all(approved=None):
        """Fetch all users or filter by approval status."""
        if not supabase:
            return []
        query = supabase.table('users').select('*')
        if approved is not None:
            query = query.eq('approved', approved)
        res = query.execute()
        return res.data or []

    @staticmethod
    def insert(user_data):
        """Insert a newly registered user record."""
        if not supabase:
            return False
        res = supabase.table('users').insert(user_data).execute()
        return bool(res.data)

    @staticmethod
    def update(username, updates):
        """Update fields on an existing user."""
        if not supabase:
            return False
        res = supabase.table('users').update(updates).eq('username', username).execute()
        return bool(res.data)

    @staticmethod
    def delete(username):
        """Delete user record and associated screenshot."""
        if not supabase:
            return False
        user = UserManager.get_by_username(username)
        if user and user.get('screenshot_url'):
            StorageManager.delete_screenshot(user['screenshot_url'])
        res = supabase.table('users').delete().eq('username', username).execute()
        return bool(res.data)
