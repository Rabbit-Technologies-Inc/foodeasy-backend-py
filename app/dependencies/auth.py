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
        decoded_token = verify_firebase_token(token)
        firebase_uid = decoded_token.get('uid')
        
        if not firebase_uid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user identifier"
            )
        
        # Get user_id from Supabase using firebase_uid
        result = auth_service.supabase.table('user_profiles') \
            .select('id') \
            .eq('firebase_uid', firebase_uid) \
            .execute()
        
        if not result.data or len(result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found. Please complete registration first."
            )
        
        user_id = result.data[0]['id']
        return user_id
        
    except firebase_auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token. Please login again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired. Please login again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
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
    if current_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this resource"
        )
    
    return user_id

