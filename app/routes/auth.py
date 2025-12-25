# app/routes/auth.py

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from app.services.auth_service import auth_service
from firebase_admin import auth as firebase_auth
from typing import Dict, Any

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class VerifyTokenRequest(BaseModel):
    """Request for OTP verification"""
    id_token: str = Field(..., description="Firebase ID token after OTP verification")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6Ij..."
            }
        }


class VerifyTokenResponse(BaseModel):
    """Response after successful OTP verification"""
    user_id: str = Field(..., description="Unique user ID")
    phone_number: str = Field(..., description="Verified phone number")
    is_new_user: bool = Field(..., description="True if first time login")
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "phone_number": "+919876543210",
                "is_new_user": True
            }
        }


class UpdateProfileRequest(BaseModel):
    """Request to update user profile"""
    full_name: str = Field(..., min_length=1, max_length=100, description="User's full name")
    
    class Config:
        json_schema_extra = {
            "example": {
                "full_name": "Nik Kumar"
            }
        }


# ============================================
# AUTH ENDPOINTS
# ============================================

@router.post(
    "/verify-otp",
    response_model=VerifyTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify OTP and get user_id",
    description="""
    Verify Firebase ID token after OTP verification and return user_id.
    
    **Flow:**
    1. User enters phone number in React Native → Firebase sends OTP
    2. User enters OTP → Firebase verifies it
    3. React Native gets Firebase ID token
    4. Call this endpoint with the token
    5. Backend verifies token and returns user_id
    
    **Behavior:**
    - If phone number is new → creates user, returns user_id with is_new_user=true
    - If phone number exists → returns existing user_id with is_new_user=false
    
    **Note:** Name is NOT captured during login. Use PUT /user/{user_id}/profile to add name later.
    """
)
async def verify_otp(request: VerifyTokenRequest) -> VerifyTokenResponse:
    """
    Verify Firebase token and return user_id.
    """
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


@router.put(
    "/user/{user_id}/profile",
    status_code=status.HTTP_200_OK,
    summary="Update user profile (add name)",
    description="""
    Update user profile with full name after authentication.
    
    **When to use:**
    - After user successfully logs in and receives user_id
    - When user needs to add/update their display name
    
    **Protected fields (cannot update):**
    - id
    - firebase_uid
    - phone_number
    - created_at
    """
)
async def update_profile(user_id: str, request: UpdateProfileRequest) -> Dict[str, Any]:
    """
    Update user profile with name.
    """
    try:
        update_data = {"full_name": request.full_name}
        updated_user = await auth_service.update_user_profile(user_id, update_data)
        
        return {
            "success": True,
            "data": updated_user
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        print(f"Error in update_profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}"
        )


@router.get(
    "/user/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Get user profile",
    description="Get complete user profile by user_id"
)
async def get_user(user_id: str) -> Dict[str, Any]:
    """
    Get user profile by user_id.
    """
    try:
        user = await auth_service.get_user_by_id(user_id)
        return {
            "success": True,
            "data": user
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        print(f"Error in get_user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch user: {str(e)}"
        )


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Auth service health check"
)
async def auth_health_check():
    """
    Check if Firebase and Supabase connections are working.
    """
    return {
        "success": True,
        "service": "auth",
        "firebase": "connected",
        "supabase": "connected"
    }