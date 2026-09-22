

from fastapi import Request, Depends
from sqlalchemy.orm import Session
from shared.db.session import get_db
from shared.db.models.user import User
from shared.auth.tokens import verify_token
from shared.repositories.user_repo import UserRepository
from shared.exceptions import AuthenticationError

user_repo = UserRepository()

def extract_bearer_token(request: Request) -> str:
    """Extracts Bearer token from HTTP Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise AuthenticationError("Authentication token is missing. Please sign in.")

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthenticationError("Invalid Authorization header format. Expected 'Bearer <token>'")

    return parts[1]

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency that validates Bearer token and returns current authenticated User entity."""
    token = extract_bearer_token(request)
    payload = verify_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Invalid token payload")

    user = user_repo.get_by_id(db, user_id)
    if not user or user.status != "ACTIVE":
        raise AuthenticationError("Authenticated user account is no longer active")

    request.state.auth_token = token
    request.state.current_user = user
    return user

def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Dependency enforcing active user status."""
    if current_user.status != "ACTIVE":
        raise AuthenticationError("User account is inactive")
    return current_user
