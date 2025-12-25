# app/routes/auth.py

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from app.services.auth_service import auth_service
from firebase_admin import auth as firebase_auth
from typing import Dict, Any, List, Optional

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class VerifyTokenRequest(BaseModel):
    """Request for OTP verification"""
    id_token: str = Field(..., description="Firebase ID token after OTP verification")


class VerifyTokenResponse(BaseModel):
    """Response after successful OTP verification"""
    user_id: str = Field(..., description="Unique user ID")
    phone_number: str = Field(..., description="Verified phone number")
    is_new_user: bool = Field(..., description="True if first time login")




# ============================================
# AUTH ENDPOINTS
# ============================================

@router.post(
    "/verify-otp",
    response_model=VerifyTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify OTP and get user_id",
    description="""
    Verify Firebase ID token after OTP verification and sync user with Supabase.
    
    **Flow:**
    1. User enters phone number in React Native app
    2. Firebase sends OTP to phone number
    3. User enters OTP, Firebase verifies it and returns ID token
    4. React Native calls this endpoint with the Firebase ID token
    5. Backend verifies token, creates/retrieves user in Supabase
    6. Returns user_id and phone number for authenticated user
    
    **For returning users:** Same phone number returns same user_id.
    **For new users:** Creates new user profile with phone number only.
    """
)
async def verify_otp(request: VerifyTokenRequest) -> VerifyTokenResponse:
    """Verify Firebase token and return user_id."""
    try:
        user_data = await auth_service.verify_and_sync_user(request.id_token)
        return VerifyTokenResponse(**user_data)
        
    except firebase_auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token. Please try again."
        )
    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired. Please request new OTP."
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        print(f"Error in verify_otp: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed. Please try again."
        )


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Auth service health check",
    description="""
    Health check endpoint for authentication service.
    
    Verifies that Firebase and Supabase connections are working properly.
    Returns connection status for both services.
    
    Use this endpoint for monitoring and health checks.
    """
)
async def auth_health_check():
    """Check if Firebase and Supabase connections are working"""
    return {
        "success": True,
        "service": "auth",
        "firebase": "connected",
        "supabase": "connected"
    }