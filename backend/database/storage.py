from backend.database.client import supabase
from backend.config.settings import logger

class StorageManager:
    @staticmethod
    def upload_screenshot(filename, file_bytes, content_type):
        """Upload image to Supabase Storage screenshots bucket."""
        if not supabase:
            return None
        supabase.storage.from_('screenshots').upload(
            path=filename,
            file=file_bytes,
            file_options={"content-type": content_type}
        )
        return supabase.storage.from_('screenshots').get_public_url(filename)

    @staticmethod
    def delete_screenshot(screenshot_url):
        """Remove image file from Supabase Storage."""
        if not supabase or not screenshot_url:
            return
        try:
            filename = screenshot_url.split('/')[-1]
            supabase.storage.from_('screenshots').remove([filename])
        except Exception as e:
            logger.warning(f"Failed to remove screenshot '{screenshot_url}': {e}")
