

import unittest
from shared.database import initialize_database
from shared.db.session import get_db_session
from shared.db.models.user import User, Role, Permission
from shared.auth.password import hash_password
from shared.auth.permissions import Permissions
from shared.repositories.user_repo import UserRepository, RoleRepository
from apps.backend.services.user_service import user_service
from apps.backend.services.role_service import role_service
from scripts.seed_rbac import seed_rbac
from shared.exceptions import ValidationError, ConflictException

class TestUserRoleManagementUnit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from shared.db.models import Base
        from shared.db.session import get_engine
        Base.metadata.create_all(bind=get_engine())
        initialize_database()
        seed_rbac()

    def test_01_rbac_seed(self):
        with get_db_session() as db:
            admin_role = RoleRepository().get_by_code(db, "ADMIN")
            self.assertIsNotNone(admin_role)
            self.assertTrue(admin_role.is_system_role)

            perm = db.query(Permission).filter(Permission.code == Permissions.USERS_VIEW).first()
            self.assertIsNotNone(perm)

    def test_02_user_creation_and_duplicate_guard(self):
        with get_db_session() as db:
            user_repo = UserRepository()
            existing = user_repo.get_by_username(db, "u_test_op")
            if existing:
                user_repo.delete(db, existing.id, hard=True)
                db.commit()

            u_data = user_service.create_user(
                db=db,
                username="u_test_op",
                full_name="Operator One",
                password="OperatorPass123!",
                role_code="OPERATOR",
                email="op1@example.com"
            )
            self.assertIsNotNone(u_data["id"])
            self.assertEqual(u_data["username"], "u_test_op")
            self.assertEqual(u_data["role_code"], "OPERATOR")

            with self.assertRaises(ConflictException):
                user_service.create_user(
                    db=db,
                    username="u_test_op",
                    full_name="Duplicate User",
                    password="Password123!",
                    email="dup@example.com"
                )

    def test_03_self_deactivation_guard(self):
        with get_db_session() as db:
            user_repo = UserRepository()
            user = user_repo.get_by_username(db, "u_test_op")
            self.assertIsNotNone(user)

            with self.assertRaises(ValidationError) as ctx:
                user_service.update_user(
                    db=db,
                    user_id=user.id,
                    status="INACTIVE",
                    acting_user_id=user.id
                )
            self.assertIn("cannot deactivate", str(ctx.exception).lower())

    def test_04_last_admin_lockout_guard(self):
        with get_db_session() as db:
            user_repo = UserRepository()
            admins = user_repo.list_users(db, role_code="ADMIN", status="ACTIVE")
            if not admins:
                user_service.create_user(
                    db=db,
                    username="admin_test_lockout",
                    full_name="Admin Lockout Test",
                    password="AdminPass123!",
                    role_code="ADMIN",
                    email="admin_lockout@example.com"
                )
                admins = user_repo.list_users(db, role_code="ADMIN", status="ACTIVE")
            if len(admins) > 1:
                for a in admins[1:]:
                    a.status = "INACTIVE"
                db.flush()

            last_admin = admins[0]
            with self.assertRaises(ValidationError) as ctx:
                user_service.update_user(
                    db=db,
                    user_id=last_admin.id,
                    status="INACTIVE",
                    acting_user_id="other-admin-id"
                )
            self.assertIn("last active administrator", str(ctx.exception).lower())

    def test_05_system_role_deletion_guard(self):
        with get_db_session() as db:
            role_repo = RoleRepository()
            admin_role = role_repo.get_by_code(db, "ADMIN")
            self.assertIsNotNone(admin_role)

            with self.assertRaises(ValidationError) as ctx:
                role_service.delete_role(db=db, role_id=admin_role.id)
            self.assertIn("system role", str(ctx.exception).lower())

if __name__ == "__main__":
    unittest.main()
