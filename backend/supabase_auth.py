"""
Supabase Auth Utilities — Session-aware database operation helpers.

Provides:
- Retry decorator for handling JWT expiration errors (PGRST303)
- Proactive session refresh utilities
- Token expiration checking

Usage:
    from backend.supabase_auth import with_auth_retry
    
    @with_auth_retry()
    def my_database_operation():
        supabase = get_supabase()
        return supabase.table("projects").select("*").execute()
"""

import functools
import time
from typing import Callable, TypeVar, Any

from backend.supabase_client import get_supabase_auth

T = TypeVar('T')


# Known Supabase/PostgREST auth error codes
AUTH_ERROR_CODES = {
    "PGRST303",  # JWT expired
    "PGRST301",  # JWT invalid
    "PGRST302",  # JWT malformed
}


def is_auth_error(error: Exception) -> bool:
    """
    Check if an exception is a Supabase authentication error.
    
    These errors indicate the JWT is expired, invalid, or malformed,
    and the operation should be retried after refreshing the session.
    """
    error_str = str(error)
    
    # Check for PostgREST error codes
    for code in AUTH_ERROR_CODES:
        if code in error_str:
            return True
    
    # Check for common auth error messages
    auth_keywords = [
        "JWT expired",
        "JWT invalid",
        "invalid token",
        "token expired",
        "Invalid Refresh Token",
    ]
    
    for keyword in auth_keywords:
        if keyword.lower() in error_str.lower():
            return True
    
    return False


def refresh_supabase_session() -> bool:
    """
    Attempt to refresh the current Supabase session.
    
    Returns:
        True if refresh succeeded, False otherwise.
    """
    try:
        supabase = get_supabase_auth()
        session = supabase.auth.get_session()
        
        if session and hasattr(session, 'refresh_token') and session.refresh_token:
            # Use the refresh token to get a new session
            response = supabase.auth.refresh_session(session.refresh_token)
            if response and response.session:
                print(f"[Auth] Session refreshed successfully")
                return True
        
        print(f"[Auth] No valid session to refresh")
        return False
        
    except Exception as e:
        print(f"[Auth] Failed to refresh session: {e}")
        return False


def with_auth_retry(max_retries: int = 1, retry_delay: float = 0.1):
    """
    Decorator that retries database operations on authentication errors.
    
    When a PGRST303 (JWT expired) or similar auth error occurs:
    1. Attempts to refresh the Supabase session
    2. Retries the operation
    3. If retry fails, propagates the original error
    
    Args:
        max_retries: Maximum number of retry attempts (default: 1)
        retry_delay: Delay in seconds between retries (default: 0.1)
    
    Usage:
        @with_auth_retry()
        def get_user_projects(user_id: str):
            supabase = get_supabase()
            return supabase.table("projects").select("*").eq("user_id", user_id).execute()
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_error = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    
                    # Check if this is an auth error we can retry
                    if is_auth_error(e) and attempt < max_retries:
                        print(f"[Auth] Auth error in {func.__name__}, attempting refresh (attempt {attempt + 1}/{max_retries})")
                        
                        # Try to refresh the session
                        if refresh_supabase_session():
                            time.sleep(retry_delay)
                            continue  # Retry the operation
                        else:
                            # Refresh failed, don't retry
                            print(f"[Auth] Session refresh failed, not retrying {func.__name__}")
                            break
                    else:
                        # Not an auth error or max retries reached
                        break
            
            # Raise the last error if all retries failed
            if last_error:
                raise last_error
            
        return wrapper
    return decorator


def with_auth_retry_async(max_retries: int = 1, retry_delay: float = 0.1):
    """
    Async version of with_auth_retry for async database operations.
    
    Usage:
        @with_auth_retry_async()
        async def get_user_projects_async(user_id: str):
            supabase = get_supabase()
            return supabase.table("projects").select("*").eq("user_id", user_id).execute()
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            import asyncio
            last_error = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    
                    if is_auth_error(e) and attempt < max_retries:
                        print(f"[Auth] Auth error in {func.__name__}, attempting refresh (attempt {attempt + 1}/{max_retries})")
                        
                        if refresh_supabase_session():
                            await asyncio.sleep(retry_delay)
                            continue
                        else:
                            print(f"[Auth] Session refresh failed, not retrying {func.__name__}")
                            break
                    else:
                        break
            
            if last_error:
                raise last_error
            
        return wrapper
    return decorator
