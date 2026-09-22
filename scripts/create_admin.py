
import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.database import initialize_database
from shared.db.session import get_db_session
from shared.db.models.user import User, Role
from shared.auth.password import hash_password
from shared.repositories.user_repo import UserRepository, RoleRepository

def main():
    parser = argparse.ArgumentParser(description="Create initial administrator user for CtrlBooks")
    parser.add_argument("--username", default="admin", help="Admin username (default: admin)")
    parser.add_argument("--name", default="Administrator", help="Admin full name (default: Administrator)")
    parser.add_argument("--email", default="admin@ctrlbooks.com", help="Admin email address")
    parser.add_argument("--password", default=None, help="Admin password (if omitted, checks ADMIN_PASSWORD env or prompts)")

    args = parser.parse_args()
    username = args.username.strip()
    full_name = args.name.strip()
    email = args.email.strip()

    password = args.password or os.getenv("ADMIN_PASSWORD")
    if not password:
        if sys.stdin.isatty():
            password = getpass.getpass(f"Enter password for admin user '{username}': ")
        else:
            password = "Admin@123"

    if not password or len(password) < 6:
        print("[!] Error: Admin password must be at least 6 characters long.")
        sys.exit(1)

    print("=========================================================")
    print(" CtrlBooks - Administrator Account Setup")
    print("=========================================================")

    initialize_database()

    with get_db_session() as db:
        user_repo = UserRepository()
        role_repo = RoleRepository()

        admin_role = role_repo.get_by_code(db, "ADMIN") or role_repo.get_by_name(db, "Admin")
        if not admin_role:
            admin_role = Role(name="Admin", code="ADMIN", description="Full system administrator access", is_system_role=True)
            admin_role = role_repo.create(db, admin_role)
            print("[+] Role 'Admin' (ADMIN) created successfully.")

        existing_user = user_repo.get_by_username(db, username)
        if existing_user:
            existing_user.password_hash = hash_password(password)
            existing_user.status = "ACTIVE"
            user_repo.update(db, existing_user, {"password_hash": existing_user.password_hash, "status": "ACTIVE"})
            role_repo.assign_role_to_user(db, existing_user.id, admin_role.id)
            print(f"[+] User '{username}' password and Admin role verified/updated.")
            return

        hashed = hash_password(password)
        new_admin = User(
            username=username,
            full_name=full_name,
            email=email,
            password_hash=hashed,
            status="ACTIVE"
        )
        created_user = user_repo.create(db, new_admin)
        role_repo.assign_role_to_user(db, created_user.id, admin_role.id)

        print(f"[+] Administrator user '{username}' ({full_name}) successfully created with Admin role!")
        print("[!] Remember to keep your admin credentials safe and secure.\n")

if __name__ == "__main__":
    main()
