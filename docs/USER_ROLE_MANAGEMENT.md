# Module 4 Architecture: Production User & Role Management (RBAC)

## Overview
Module 4 expands the CtrlBooks authentication architecture by adding complete, production-grade **User Management** and **Role-Based Access Control (RBAC)**. 

---

## Key Features

1. **Role-Based Access Control (RBAC)**:
   - Granular machine-readable permission string codes (e.g. `users.view`, `users.create`, `users.update`, `roles.view`, `connectors.view`, `sync.start`).
   - System Roles (`ADMIN`, `OPERATOR`, `VIEWER`) seeded automatically via `scripts/seed_rbac.py`.
   - Authorization middleware dependency `require_permission(permission_code)`.

2. **User Management Service**:
   - Paginated user list with full-text search across username, full name, and email.
   - User creation with instant PBKDF2-HMAC-SHA256 password hashing and role assignment.
   - Status transitions (`ACTIVE`, `INACTIVE`, `LOCKED`, `DISABLED`).
   - Password reset with session revocation.

3. **Administrative Safety Guards**:
   - **Self-Deactivation Protection**: An administrator cannot deactivate or disable their own active account.
   - **Last Active Admin Lockout Protection**: Deactivating or modifying the last remaining active `ADMIN` user is strictly blocked by business logic.
   - **System Role Protection**: Default system roles (`ADMIN`, `OPERATOR`, `VIEWER`) cannot be deleted or renamed.

4. **PySide6 Desktop GUI**:
   - Users Page connected directly to `/api/users` with real-time status badges, user creation modal, password reset, and activation/deactivation toggles.
   - Roles & Permissions Page connected directly to `/api/roles` displaying assigned permission lists and active user counts per role.

---

## API Summary

| Method | Endpoint | Required Permission | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/users` | `users.view` | List users with pagination and search |
| `GET` | `/api/users/{id}` | `users.view` | Get user profile details |
| `POST` | `/api/users` | `users.create` | Create user with password hash |
| `PUT` | `/api/users/{id}` | `users.update` | Update profile, role, or status |
| `POST` | `/api/users/{id}/activate` | `users.update` | Activate user account |
| `POST` | `/api/users/{id}/deactivate` | `users.update` | Deactivate user account |
| `POST` | `/api/users/{id}/reset-password` | `users.update` | Reset password & revoke active sessions |
| `GET` | `/api/roles` | `roles.view` | List all system & custom roles |
| `POST` | `/api/roles` | `roles.create` | Create custom role with permissions |
| `PUT` | `/api/roles/{id}` | `roles.update` | Modify role permissions/details |
| `DELETE` | `/api/roles/{id}` | `roles.delete` | Delete custom role (system roles protected) |
| `GET` | `/api/permissions` | `roles.view` | List all system permissions by module |

---

## Automated Verification
Run the complete automated verification pipeline:
```bash
python scripts/verify_all.py
```
