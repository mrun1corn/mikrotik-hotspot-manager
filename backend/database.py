from supabase import create_client, Client

try:
    from backend.config import SUPABASE_URL, SUPABASE_KEY, logger
except ImportError:
    from config import SUPABASE_URL, SUPABASE_KEY, logger

class Database:
    def __init__(self, url=None, key=None):
        self.url = url or SUPABASE_URL
        self.key = key or SUPABASE_KEY
        self.client: Client = create_client(self.url, self.key) if self.url and self.key else None

    def get_user_by_username(self, username):
        """Fetch a single user row by username."""
        if not self.client:
            return None
        res = self.client.table('users').select('*').eq('username', username).execute()
        return res.data[0] if res.data else None

    def get_all_users(self, approved=None):
        """Fetch all users or filter by approval status."""
        if not self.client:
            return []
        query = self.client.table('users').select('*')
        if approved is not None:
            query = query.eq('approved', approved)
        res = query.execute()
        return res.data or []

    def insert_user(self, user_data):
        """Insert a newly registered user record."""
        if not self.client:
            return False
        res = self.client.table('users').insert(user_data).execute()
        return bool(res.data)

    def update_user(self, username, updates):
        """Update fields on an existing user."""
        if not self.client:
            return False
        res = self.client.table('users').update(updates).eq('username', username).execute()
        return bool(res.data)

    def delete_user(self, username):
        """Delete user record and associated screenshot."""
        if not self.client:
            return False
        user = self.get_user_by_username(username)
        if user and user.get('screenshot_url'):
            self.delete_screenshot(user['screenshot_url'])
        res = self.client.table('users').delete().eq('username', username).execute()
        return bool(res.data)

    def upload_screenshot(self, filename, file_bytes, content_type):
        """Upload image to Supabase Storage screenshots bucket."""
        if not self.client:
            return None
        self.client.storage.from_('screenshots').upload(
            path=filename,
            file=file_bytes,
            file_options={"content-type": content_type}
        )
        return self.client.storage.from_('screenshots').get_public_url(filename)

    def delete_screenshot(self, screenshot_url):
        """Remove image file from Supabase Storage."""
        if not self.client or not screenshot_url:
            return
        try:
            filename = screenshot_url.split('/')[-1]
            self.client.storage.from_('screenshots').remove([filename])
        except Exception as e:
            logger.warning(f"Failed to remove screenshot '{screenshot_url}': {e}")

# Singleton instance
db = Database()
