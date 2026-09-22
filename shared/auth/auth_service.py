

from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from shared.auth.password import verify_password, hash_password
from shared.auth.tokens import create_access_token, revoke_token
from shared.auth.rate_limiter import rate_limiter
from shared.repositories.user_repo import UserRepository, RoleRepository
from shared.repositories.system_repo import ActivityLogRepository
from shared.exceptions import AuthenticationError, ValidationError
from shared.db.base import utc_now
from shared.logging_config import get_logger

from shared.auth.resend_service import resend_service
from shared.auth.otp_service import otp_service
from shared.db.models.user import User

logger = get_logger("app.auth.service")

class AuthService:
    def __init__(self):
        self.user_repo = UserRepository()
        self.role_repo = RoleRepository()
        self.audit_repo = ActivityLogRepository()

    def send_email_otp(self, email: str) -> Dict[str, Any]:
        """Generates OTP and sends it via Resend API."""
        clean_email = (email or "").strip().lower()
        if not clean_email or "@" not in clean_email:
            raise ValidationError("Valid email address is required")

        rate_limiter.check_rate_limit(clean_email)

        otp_code = otp_service.generate_otp(clean_email)
        resend_result = resend_service.send_otp_email(clean_email, otp_code)

        return {
            "status": "success",
            "email": clean_email,
            "message": f"OTP sent to {clean_email}",
            "resend_details": resend_result
        }

    def verify_email_otp(
        self,
        db: Session,
        email: str,
        otp: str,
        client_ip: str = "127.0.0.1",
        request_id: str = ""
    ) -> Dict[str, Any]:
        """Verifies OTP, authenticates or creates user, and returns session token."""
        clean_email = (email or "").strip().lower()
        clean_otp = (otp or "").strip()

        if not clean_email or not clean_otp:
            raise ValidationError("Email address and OTP code are required")

        rate_limiter.check_rate_limit(clean_email)

        ok, msg = otp_service.verify_otp(clean_email, clean_otp)
        if not ok:
            rate_limiter.record_failed_attempt(clean_email)
            self._log_audit(db, None, "LOGIN_FAILED", f"Failed OTP verification for '{clean_email}': {msg}", request_id)
            raise AuthenticationError(msg)

        rate_limiter.clear_failed_attempts(clean_email)

        user = self.user_repo.get_by_email(db, clean_email)
        if not user:
            user = self.user_repo.get_by_username(db, clean_email)

        if not user:
            username_val = clean_email.split("@")[0]
            base_username = username_val
            idx = 1
            while self.user_repo.get_by_username(db, username_val):
                username_val = f"{base_username}{idx}"
                idx += 1

            user = User(
                username=username_val,
                email=clean_email,
                full_name=username_val.title(),
                password_hash=hash_password("OtpUserDefaultPassword123!"),
                status="ACTIVE"
            )
            db.add(user)
            db.flush()

        user.last_login_at = utc_now()
        db.flush()

        role_name = "User"
        if user.user_roles:
            role_obj = user.user_roles[0].role
            if role_obj:
                role_name = role_obj.name
        elif "admin" in clean_email:
            role_name = "Admin"

        self._log_audit(db, user.id, "LOGIN_SUCCESS", f"User '{clean_email}' signed in via OTP successfully", request_id)

        expires_delta = timedelta(hours=24)
        expires_at = datetime.now(timezone.utc) + expires_delta

        token_payload = {
            "sub": user.id,
            "username": user.username,
            "email": clean_email,
            "role": role_name,
        }
        token = create_access_token(token_payload, expires_delta=expires_delta)

        return {
            "user": {
                "id": user.id,
                "username": user.username,
                "email": clean_email,
                "full_name": user.full_name,
                "role": role_name,
                "status": user.status
            },
            "session": {
                "access_token": token,
                "expires_at": expires_at.isoformat()
            }
        }

    def authenticate_user(
        self,
        db: Session,
        username: str,
        password: str,
        client_ip: str = "127.0.0.1",
        request_id: str = ""
    ) -> Dict[str, Any]:
        """
        Authenticates username and password against database.
        Returns generic 'Invalid username or password' on any credential/status mismatch to prevent enumeration.
        """
        clean_username = (username or "").strip()
        if not clean_username or not password:
            raise AuthenticationError("Invalid username or password")

        rate_limiter.check_rate_limit(clean_username)

        user = self.user_repo.get_by_username(db, clean_username)
        if not user:
            rate_limiter.record_failed_attempt(clean_username)
            self._log_audit(db, None, "LOGIN_FAILED", f"Failed login attempt for username '{clean_username}' (user not found)", request_id)
            raise AuthenticationError("Invalid username or password")

        if user.status != "ACTIVE":
            rate_limiter.record_failed_attempt(clean_username)
            self._log_audit(db, user.id, "LOGIN_FAILED", f"Login attempt for inactive user '{clean_username}' (Status={user.status})", request_id)
            raise AuthenticationError("Invalid username or password")

        if not verify_password(password, user.password_hash):
            rate_limiter.record_failed_attempt(clean_username)
            self._log_audit(db, user.id, "LOGIN_FAILED", f"Failed login attempt for user '{clean_username}' (invalid password)", request_id)
            raise AuthenticationError("Invalid username or password")

        rate_limiter.clear_failed_attempts(clean_username)
        user.last_login_at = utc_now()
        db.flush()

        role_name = "User"
        if user.user_roles:
            role_obj = user.user_roles[0].role
            if role_obj:
                role_name = role_obj.name
        elif "admin" in clean_username.lower():
            role_name = "Admin"

        self._log_audit(db, user.id, "LOGIN_SUCCESS", f"User '{user.username}' signed in successfully", request_id)

        expires_delta = timedelta(hours=24)
        expires_at = datetime.now(timezone.utc) + expires_delta

        token_payload = {
            "sub": user.id,
            "username": user.username,
            "role": role_name,
        }
        token = create_access_token(token_payload, expires_delta=expires_delta)

        logger.info(f"User '{user.username}' authenticated successfully (Role={role_name})")

        return {
            "user": {
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "role": role_name,
                "status": user.status
            },
            "session": {
                "access_token": token,
                "expires_at": expires_at.isoformat()
            }
        }

    def get_current_user_profile(self, db: Session, user_id: str) -> Dict[str, Any]:
        """Returns authenticated user profile information."""
        user = self.user_repo.get_by_id_or_raise(db, user_id)
        role_name = "User"
        if user.user_roles:
            role_obj = user.user_roles[0].role
            if role_obj:
                role_name = role_obj.name
        elif "admin" in user.username.lower():
            role_name = "Admin"

        return {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": role_name,
            "status": user.status,
            "email": user.email,
            "created_at": user.created_at.isoformat()
        }

    def logout_user(self, db: Session, token: str, user_id: Optional[str] = None, request_id: str = "") -> None:
        """Revokes authentication token and logs logout audit event."""
        revoke_token(token)
        self._log_audit(db, user_id, "LOGOUT", "User logged out cleanly", request_id)

    def _log_audit(self, db: Session, user_id: Optional[str], event_type: str, message: str, request_id: str) -> None:
        try:
            self.audit_repo.log_activity(
                db=db,
                event_type=event_type,
                status="SUCCESS" if "SUCCESS" in event_type or event_type == "LOGOUT" else "FAILED",
                message=message,
                user_id=user_id,
                request_id=request_id
            )
        except Exception as exc:
            logger.error(f"Failed to record auth audit event: {exc}")

auth_service = AuthService()
