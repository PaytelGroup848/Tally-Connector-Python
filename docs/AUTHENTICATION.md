# CtrlBooks — Authentication & User Login System (Module 3)

This document details the production-ready **Username + Password Authentication System** implemented in **Module 3**.

---

## 1. Authentication Architecture

```
User Input (Username + Password)
          ↓
Backend Authentication Service (shared/auth/auth_service.py)
          ↓
Rate Limiter Check (shared/auth/rate_limiter.py)
          ↓
UserRepository Lookup (shared/repositories/user_repo.py)
          ↓
Account Status Verification (ACTIVE?)
          ↓
PBKDF2-HMAC-SHA256 Password Hash Verification (shared/auth/password.py)
          ↓
Generate Signed HMAC-SHA256 Access Token (shared/auth/tokens.py)
          ↓
Audit Log Entry (LOGIN_SUCCESS)
          ↓
Return Safe User Info + Session Token
```

---

## 2. Security & Credentials Policies

1. **Password Hashing**: Passwords are saved as `pbkdf2:sha256:100000$<salt_hex>$<hash_hex>` with a 16-byte random salt and 100,000 iterations.
2. **No Plain-Text Storage or Leakage**: Plain text passwords, password hashes, and secret keys are never logged, returned in API responses, or embedded inside tokens.
3. **Generic Error Message**: All invalid login attempts (whether non-existent username, wrong password, or inactive account) return HTTP 401 with the generic error message `"Invalid username or password"`. This prevents username enumeration attacks.
4. **Brute-Force Rate Limiting**: The `LoginRateLimiter` enforces a threshold of max 5 failed login attempts per username/IP within 5 minutes, returning HTTP 429 Too Many Requests upon lockout.
5. **Token Revocation**: Calling `POST /api/auth/logout` adds the access token to the revocation blacklist. Subsequent API calls with a revoked token are rejected with HTTP 401 Unauthorized.

---

## 3. API Endpoints

### `POST /api/auth/login`
- **Request**:
  ```json
  {
    "username": "admin",
    "password": "Admin@123"
  }
  ```
- **Response**:
  ```json
  {
    "success": true,
    "data": {
      "user": {
        "id": "usr-uuid-123",
        "username": "admin",
        "full_name": "Administrator",
        "role": "Admin",
        "status": "ACTIVE"
      },
      "session": {
        "access_token": "eyJhbGciOiJIUzI1NiJ9...",
        "expires_at": "2026-08-23T15:20:00Z"
      }
    },
    "message": "Login successful",
    "request_id": "req-123"
  }
  ```

### `POST /api/auth/logout`
- **Headers**: `Authorization: Bearer <access_token>`
- **Response**:
  ```json
  {
    "success": true,
    "data": { "logged_out": true },
    "message": "Logged out successfully",
    "request_id": "req-124"
  }
  ```

### `GET /api/auth/me`
- **Headers**: `Authorization: Bearer <access_token>`
- **Response**:
  ```json
  {
    "success": true,
    "data": {
      "id": "usr-uuid-123",
      "username": "admin",
      "full_name": "Administrator",
      "role": "Admin",
      "status": "ACTIVE",
      "email": "admin@ctrlbooks.com"
    },
    "message": "User profile retrieved successfully",
    "request_id": "req-125"
  }
  ```

---

## 4. Admin Bootstrap CLI Utility

To safely initialize the default administrator account in development or production without hardcoding passwords:

```powershell
python scripts/create_admin.py --username admin --name "Administrator" --email "admin@ctrlbooks.com"
```

The script will prompt for a password securely or read from `ADMIN_PASSWORD` environment variable. If the administrator user already exists in the database, the command will preserve the existing password without overwriting.

---

## 5. Desktop Application Integration

The PySide6 Desktop GUI ([`apps/desktop_app/ui/pages/login_page.py`](file:///c:/Users/Sales/Desktop/CtrlBooks/apps/desktop_app/ui/pages/login_page.py)) connects directly to the backend API:
- Performs asynchronous background HTTP request via `LoginWorker` thread to prevent UI freezing.
- Disables button and displays `"Authenticating..."` during request.
- Displays safe red error banner `⚠️ Invalid username or password` on credential failure.
- Supports Show/Hide password toggle and Enter key submission.
- On success, stores `access_token` in memory and navigates to the main Dashboard.
