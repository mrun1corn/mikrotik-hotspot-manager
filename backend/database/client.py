from supabase import create_client, Client
from backend.config.settings import SUPABASE_URL, SUPABASE_KEY, logger

class SupabaseConnection:
    _instance = None

    @classmethod
    def get_client(cls) -> Client:
        if cls._instance is None:
            if SUPABASE_URL and SUPABASE_KEY:
                try:
                    cls._instance = create_client(SUPABASE_URL, SUPABASE_KEY)
                except Exception as e:
                    logger.error(f"Failed to initialize Supabase client: {e}")
            else:
                logger.warning("Supabase URL or Key not set")
        return cls._instance

supabase = SupabaseConnection.get_client()
