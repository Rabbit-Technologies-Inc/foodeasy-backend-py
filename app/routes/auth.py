# app/routes/auth.py

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from app.services.auth_service import auth_service
from typing import Dict, Any
import re

router = APIRouter(prefix="/auth", tags=["Authentication"])

# E.164 phone pattern
PHONE_PATTERN = re.compile(r"^\+[1-9]\d{1,14}$")


# ========== Request/Response models ==========


class SendOtpRequest(BaseModel):
    phone_number: str = Field(..., description="Phone number in E.164 format (e.g. +919952907025)")


class VerifyOtpRequest(BaseModel):
    phone_number: str = Field(..., description="Phone number in E.164 format")
    otp_code: str = Field(..., min_length=4, max_length=10, description="OTP code received via SMS")


class VerifyOtpResponse(BaseModel):
    user_id: str
    phone_number: str
    is_new_user: bool
    access_token: str
    expires_in: int | None = None  # None = effectively infinite


# ========== Endpoints ==========


@router.post(
    "/send-otp",
    status_code=status.HTTP_200_OK,
    summary="Send OTP",
    description="Send OTP to the given phone number via Twilio Verify (SMS). Rate limit per phone in production.",
)
async def send_otp(request: SendOtpRequest) -> Dict[str, Any]:
    if not PHONE_PATTERN.match(request.phone_number):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number. Use E.164 format (e.g. +919952907025)",
        )
    try:
        auth_service.send_otp(request.phone_number)
        return {
            "success": True,
            "message": "Verification code sent.",
            "phone_number": request.phone_number,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to send verification code.",
        )


@router.post(
    "/verify-otp",
    response_model=VerifyOtpResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify OTP and get access token",
    description="Verify OTP with Twilio, then return user_id and backend JWT (access_token). Use access_token as Bearer for all other APIs.",
)
async def verify_otp(request: VerifyOtpRequest) -> VerifyOtpResponse:
    if not PHONE_PATTERN.match(request.phone_number):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number. Use E.164 format.",
        )
    try:
        data = await auth_service.verify_otp_and_issue_tokens(
            request.phone_number,
            request.otp_code.strip(),
        )
        return VerifyOtpResponse(
            user_id=data["user_id"],
            phone_number=data["phone_number"],
            is_new_user=data["is_new_user"],
            access_token=data["access_token"],
            expires_in=None,  # infinite expiry
        )
    except ValueError as e:
        msg = str(e).lower()
        if "deactivated" in msg:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        if "invalid" in msg or "expired" in msg or "verification" in msg:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(f"verify_otp error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verification failed.",
        )


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Auth health check",
)
async def auth_health() -> Dict[str, Any]:
    return {
        "success": True,
        "service": "auth",
        "auth": "backend_jwt",
        "otp": "twilio_verify",
    }
