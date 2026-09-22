

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from shared.db.session import get_db
from shared.db.models.user import User
from shared.auth.auth_service import auth_service
from shared.auth.dependencies import get_current_user, extract_bearer_token
from shared.response import success_response
from shared.exceptions import ValidationError

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class SendOTPRequest(BaseModel):
    email: str = Field(..., description="Recipient email address for OTP", min_length=3, max_length=150)

class VerifyOTPRequest(BaseModel):
    email: str = Field(..., description="Recipient email address", min_length=3, max_length=150)
    otp: str = Field(..., description="6-digit OTP verification code", min_length=1, max_length=10)

class LoginRequest(BaseModel):
    username: str = Field(default="", description="User login username or email")
    password: str = Field(default="", description="User login password")
    email: str = Field(default="", description="User email for OTP login")
    otp: str = Field(default="", description="OTP code")

@router.post("/send-otp")
async def send_otp_endpoint(request: Request, body: SendOTPRequest):
    """Sends 6-digit OTP to specified email address via Resend API."""
    req_id = getattr(request.state, "request_id", "")
    result = auth_service.send_email_otp(email=body.email)
    return success_response(
        data=result,
        message=f"OTP sent to {body.email}",
        request_id=req_id
    )

@router.post("/verify-otp")
async def verify_otp_endpoint(request: Request, body: VerifyOTPRequest, db: Session = Depends(get_db)):
    """Verifies 6-digit OTP and returns authenticated session access token."""
    req_id = getattr(request.state, "request_id", "")
    client_ip = request.client.host if request.client else "127.0.0.1"
    result = auth_service.verify_email_otp(
        db=db,
        email=body.email,
        otp=body.otp,
        client_ip=client_ip,
        request_id=req_id
    )
    return success_response(
        data=result,
        message="OTP verified successfully. Login complete.",
        request_id=req_id
    )

@router.post("/login")
async def login_endpoint(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate via Email OTP or Username/Password fallback."""
    req_id = getattr(request.state, "request_id", "")
    client_ip = request.client.host if request.client else "127.0.0.1"

    if body.email and body.otp:
        result = auth_service.verify_email_otp(
            db=db,
            email=body.email,
            otp=body.otp,
            client_ip=client_ip,
            request_id=req_id
        )
        return success_response(data=result, message="Login successful", request_id=req_id)

    if body.username and body.password:
        result = auth_service.authenticate_user(
            db=db,
            username=body.username,
            password=body.password,
            client_ip=client_ip,
            request_id=req_id
        )
        return success_response(data=result, message="Login successful", request_id=req_id)

    raise ValidationError("Email and OTP or Username and Password are required")

@router.post("/logout")
async def logout_endpoint(request: Request, db: Session = Depends(get_db)):
    """Invalidate current session access token."""
    req_id = getattr(request.state, "request_id", "")
    token = extract_bearer_token(request)
    user_id = getattr(request.state, "current_user", None)
    u_id = user_id.id if user_id else None

    auth_service.logout_user(db=db, token=token, user_id=u_id, request_id=req_id)

    return success_response(
        data={"logged_out": True},
        message="Logged out successfully",
        request_id=req_id
    )

@router.get("/me")
async def current_user_endpoint(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return currently authenticated user profile."""
    req_id = getattr(request.state, "request_id", "")
    profile = auth_service.get_current_user_profile(db=db, user_id=current_user.id)
    return success_response(
        data=profile,
        message="User profile retrieved successfully",
        request_id=req_id
    )
