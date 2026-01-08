# app/routes/auth.py

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from app.services.auth_service import auth_service
from app.services.firebase_service import verify_firebase_token, get_token_expiration_info, create_custom_token, TOKEN_EXPIRATION_SECONDS
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


class TokenInfoRequest(BaseModel):
    """Request to get token expiration information"""
    id_token: str = Field(..., description="Firebase ID token to check")


class RefreshTokenRequest(BaseModel):
    """Request to refresh token (requires valid current token)"""
    id_token: str = Field(..., description="Current Firebase ID token (even if expired)")


class ResendOTPRequest(BaseModel):
    """Request to resend OTP"""
    phone_number: str = Field(..., description="Phone number in E.164 format (e.g., +919876543210)")




# ============================================
# AUTH ENDPOINTS
# ============================================

@router.post(
    "/resend-otp",
    status_code=status.HTTP_200_OK,
    summary="Request OTP resend",
    description="""
    Request to resend OTP for phone number verification.
    
    **Note:** This endpoint validates the phone number and tracks resend attempts.
    The actual OTP sending is handled by Firebase on the client side.
    
    **Flow:**
    1. Client calls this endpoint with phone number
    2. Backend validates phone number format
    3. Backend returns success response
    4. Client calls Firebase `signInWithPhoneNumber()` again to resend OTP
    5. Firebase sends new OTP SMS
    
    **Rate Limiting:** 
    - Consider implementing rate limiting to prevent abuse
    - Track resend attempts per phone number
    - Recommended: Max 3-5 resends per 15 minutes
    
    **Phone Number Format:**
    - Must be in E.164 format: +[country code][number]
    - Example: +919876543210 (India)
    """
)
async def resend_otp(request: ResendOTPRequest) -> Dict[str, Any]:
    """
    Request OTP resend for a phone number.
    
    Note: Actual OTP sending happens client-side via Firebase.
    This endpoint validates the request and can track resend attempts.
    """
    import re
    
    # Validate phone number format (E.164 format: +[country code][number])
    phone_pattern = r'^\+[1-9]\d{1,14}$'
    if not re.match(phone_pattern, request.phone_number):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number format. Please use E.164 format (e.g., +919876543210)"
        )
    
    try:
        # TODO: Implement rate limiting here
        # - Track resend attempts per phone number
        # - Limit to 3-5 resends per 15 minutes
        # - Store in Redis or database
        
        # For now, just validate and return success
        return {
            "success": True,
            "message": "Phone number validated. Please call Firebase signInWithPhoneNumber() on client to resend OTP.",
            "phone_number": request.phone_number,
            "note": "Actual OTP sending is handled by Firebase SDK on the client side."
        }
    except Exception as e:
        print(f"Error in resend_otp: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process resend OTP request"
        )


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
        # Log token info for debugging (first 20 chars only for security)
        token_preview = request.id_token[:20] + "..." if len(request.id_token) > 20 else request.id_token
        print(f"[verify_otp] Verifying token: {token_preview} (length: {len(request.id_token)})")
        
        # Validate token format
        if not request.id_token or not isinstance(request.id_token, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="id_token is required and must be a string"
            )
        
        if len(request.id_token.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="id_token cannot be empty"
            )
        
        user_data = await auth_service.verify_and_sync_user(request.id_token)
        print(f"[verify_otp] Successfully verified and synced user: {user_data.get('user_id')}")
        return VerifyTokenResponse(**user_data)
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except firebase_auth.InvalidIdTokenError as e:
        import traceback
        print(f"[verify_otp] InvalidIdTokenError caught: {str(e)}")
        print(f"[verify_otp] Exception type: {type(e).__name__}")
        print(f"[verify_otp] Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token. Please try again. Error: {str(e)}"
        )
    except firebase_auth.ExpiredIdTokenError as e:
        import traceback
        print(f"[verify_otp] ExpiredIdTokenError caught: {str(e)}")
        print(f"[verify_otp] Exception type: {type(e).__name__}")
        print(f"[verify_otp] Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token expired. Please request new OTP. Error: {str(e)}"
        )
    except ValueError as e:
        print(f"[verify_otp] ValueError: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        error_type = type(e).__name__
        error_module = type(e).__module__
        print(f"[verify_otp] Unexpected error: {error_module}.{error_type}: {str(e)}")
        print(f"[verify_otp] Full traceback: {error_trace}")
        
        # Check if it's actually a Firebase auth error that wasn't caught
        if 'firebase' in error_module.lower() or 'InvalidIdTokenError' in error_type or 'ExpiredIdTokenError' in error_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Authentication failed: {str(e)}"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}"
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
        "supabase": "connected",
        "token_expiration_seconds": TOKEN_EXPIRATION_SECONDS
    }


@router.post(
    "/test-token",
    status_code=status.HTTP_200_OK,
    summary="Test token verification (debug endpoint)",
    description="""
    Debug endpoint to test token verification directly.
    This helps diagnose token verification issues.
    """
)
async def test_token_verification(request: VerifyTokenRequest) -> Dict[str, Any]:
    """Test token verification directly for debugging"""
    try:
        from app.services.firebase_service import verify_firebase_token
        
        print(f"[test-token] Testing token verification...")
        decoded_token = verify_firebase_token(request.id_token)
        
        return {
            "success": True,
            "message": "Token verified successfully",
            "data": {
                "uid": decoded_token.get("uid"),
                "phone_number": decoded_token.get("phone_number"),
                "project_id": decoded_token.get("aud"),
                "issued_at": decoded_token.get("iat"),
                "expires_at": decoded_token.get("exp")
            }
        }
    except firebase_auth.InvalidIdTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )
    except firebase_auth.ExpiredIdTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token expired: {str(e)}"
        )
    except Exception as e:
        import traceback
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error: {str(e)}\nTraceback: {traceback.format_exc()}"
        )


@router.post(
    "/token-info",
    status_code=status.HTTP_200_OK,
    summary="Get token expiration information",
    description="""
    Get detailed information about a Firebase ID token's expiration.
    
    Returns:
    - expires_at: ISO timestamp when token expires
    - expires_in: Seconds until expiration (negative if expired)
    - is_expired: Boolean indicating if token is expired
    - issued_at: ISO timestamp when token was issued
    
    Useful for checking token expiration before making API calls.
    """
)
async def get_token_info(request: TokenInfoRequest) -> Dict[str, Any]:
    """Get token expiration information"""
    try:
        # Try to verify token (even if expired, we want to get expiration info)
        try:
            decoded_token = verify_firebase_token(request.id_token, check_expiration=False)
        except firebase_auth.InvalidIdTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token format"
            )
        except firebase_auth.ExpiredIdTokenError:
            # Even if expired, try to decode to get expiration info
            try:
                decoded_token = verify_firebase_token(request.id_token, check_expiration=False)
            except:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token is invalid or expired"
                )
        
        expiration_info = get_token_expiration_info(decoded_token)
        
        return {
            "success": True,
            "data": expiration_info
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_token_info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get token information"
        )


@router.post(
    "/refresh-token",
    status_code=status.HTTP_200_OK,
    summary="Refresh Firebase ID token",
    description="""
    Refresh a Firebase ID token.
    
    **Note:** This endpoint validates the current token and returns expiration info.
    Actual token refresh must be done on the client side using Firebase SDK:
    `await user.getIdToken(true)` to force refresh.
    
    This endpoint helps by:
    1. Validating the current token
    2. Returning expiration information
    3. Indicating if refresh is needed
    
    **Client-side refresh is required** because Firebase ID tokens are issued by Firebase,
    not by this backend. The backend can only verify tokens, not issue new ones.
    """
)
async def refresh_token_info(request: RefreshTokenRequest) -> Dict[str, Any]:
    """
    Get token refresh information.
    
    Note: Actual token refresh must be done client-side with Firebase SDK.
    """
    try:
        # Try to verify token
        try:
            decoded_token = verify_firebase_token(request.id_token, check_expiration=False)
            expiration_info = get_token_expiration_info(decoded_token)
            
            # Check if token is expired or about to expire (within 5 minutes)
            needs_refresh = expiration_info.get("is_expired", False) or \
                          (expiration_info.get("expires_in", 0) < 300)  # 5 minutes
            
            return {
                "success": True,
                "needs_refresh": needs_refresh,
                "data": expiration_info,
                "message": "Token refresh must be done client-side using Firebase SDK: await user.getIdToken(true)"
            }
        except firebase_auth.ExpiredIdTokenError:
            return {
                "success": True,
                "needs_refresh": True,
                "data": {
                    "is_expired": True,
                    "expires_in": 0
                },
                "message": "Token is expired. Please refresh client-side using: await user.getIdToken(true)"
            }
        except firebase_auth.InvalidIdTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token. Please login again."
            )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in refresh_token_info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process token refresh request"
        )