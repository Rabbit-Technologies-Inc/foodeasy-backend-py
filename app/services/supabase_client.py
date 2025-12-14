from supabase import create_client, Client
from dotenv import load_dotenv
import os
from typing import Optional

# Load environment variables
load_dotenv()

# Supabase credentials
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Validate required environment variables
if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL environment variable is not set")
if not SUPABASE_KEY:
    raise ValueError("SUPABASE_KEY environment variable is not set")
if not SUPABASE_SERVICE_ROLE_KEY:
    raise ValueError("SUPABASE_SERVICE_ROLE_KEY environment variable is not set")

# Create clients
supabase: Optional[Client] = None
supabase_admin: Optional[Client] = None

try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
except Exception as e:
    raise RuntimeError(f"Failed to create Supabase clients: {str(e)}")


def get_supabase_client() -> Client:
    """
    Get regular Supabase client (respects Row Level Security - RLS).
    
    This client uses the anon/public key and respects RLS policies.
    Use this for client-side operations where you want security policies enforced.
    
    Returns:
        Client: Supabase client instance with RLS enabled
    """
    if supabase is None:
        raise RuntimeError("Supabase client not initialized")
    return supabase


def get_supabase_admin() -> Client:
    """
    Get admin Supabase client (bypasses Row Level Security - RLS).
    
    This client uses the service role key and bypasses all RLS policies.
    Use this for server-side operations that need full database access.
    WARNING: Only use this in secure server environments, never expose to clients.
    
    Returns:
        Client: Supabase admin client instance with RLS bypassed
    """
    if supabase_admin is None:
        raise RuntimeError("Supabase admin client not initialized")
    return supabase_admin