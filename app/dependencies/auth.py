# app/dependencies/auth.py

from fastapi import Header, HTTPException, status, Depends
from typing import Optional
from app.services.firebase_service import verify_firebase_token
from app.services.auth_service import auth_service
from firebase_admin import auth as firebase_auth


async def get_current_user_id(
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> str:
    """
    FastAPI dependency to verify Firebase token and get authenticated user_id.
    
    Expects Authorization header in format: "Bearer <firebase_id_token>"
    
    Returns:
        str: user_id from Supabase (not firebase_uid)
        
    Raises:
        HTTPException: 401 if token is missing, invalid, or expired
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract token from "Bearer <token>"
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError("Invalid authorization scheme")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify Firebase token
    try:
        print(f"[get_current_user_id] Verifying token (length: {len(token)})")
        decoded_token = verify_firebase_token(token)
        firebase_uid = decoded_token.get('uid')
        
        print(f"[get_current_user_id] Token verified. Firebase UID: {firebase_uid}")
        
        if not firebase_uid:
            print(f"[get_current_user_id] ERROR: Missing firebase_uid in decoded token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user identifier"
            )
        
        # Get user_id from Supabase using firebase_uid
        print(f"[get_current_user_id] Looking up user in Supabase with firebase_uid: {firebase_uid}")
        result = auth_service.supabase.table('user_profiles') \
            .select('id, is_active') \
            .eq('firebase_uid', firebase_uid) \
            .execute()
        
        print(f"[get_current_user_id] Supabase query result: {result.data}")
        
        if not result.data or len(result.data) == 0:
            print(f"[get_current_user_id] ERROR: User not found in Supabase for firebase_uid: {firebase_uid}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found. Please complete registration first by calling /auth/verify-otp."
            )
        
        user = result.data[0]
        user_id = user.get('id')
        
        # Check if user is inactive
        is_active = user.get('is_active', True)  # Default to True if field doesn't exist
        if not is_active:
            print(f"[get_current_user_id] ERROR: User {user_id} is inactive")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account has been deactivated. Please contact support."
            )
        
        # Ensure user_id is always a string for consistent comparison
        user_id_str = str(user_id)
        print(f"[get_current_user_id] Successfully authenticated user_id: {user_id_str} (type: {type(user_id).__name__})")
        return user_id_str
        
    except firebase_auth.InvalidIdTokenError as e:
        print(f"[get_current_user_id] InvalidIdTokenError: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token. Please login again. Error: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except firebase_auth.ExpiredIdTokenError as e:
        print(f"[get_current_user_id] ExpiredIdTokenError: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token expired. Please login again. Error: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        import traceback
        print(f"[get_current_user_id] Unexpected error: {type(e).__name__}: {str(e)}")
        print(f"[get_current_user_id] Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def verify_user_access(
    user_id: str,
    current_user_id: str = Depends(get_current_user_id)
) -> str:
    """
    Verify that the authenticated user matches the requested user_id.
    
    This ensures users can only access their own data.
    
    Args:
        user_id: The user_id from the URL path
        current_user_id: The authenticated user_id from the token
        
    Returns:
        str: The verified user_id
        
    Raises:
        HTTPException: 403 if user tries to access another user's data
    """
    # Ensure both are strings for comparison (URL params are strings, but DB might return int)
    current_user_id_str = str(current_user_id)
    user_id_str = str(user_id)
    
    print(f"[verify_user_access] Comparing: current_user_id='{current_user_id_str}' (type: {type(current_user_id).__name__}) vs user_id='{user_id_str}' (type: {type(user_id).__name__})")
    
    if current_user_id_str != user_id_str:
        print(f"[verify_user_access] ❌ MISMATCH! Access denied.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You don't have permission to access this resource. Your user_id is {current_user_id_str}, but you're trying to access {user_id_str}"
        )
    
    print(f"[verify_user_access] ✓ Match! Access granted.")
    return user_id_str

