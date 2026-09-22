

import sys
from pathlib import Path
from sqlalchemy import or_, func

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.database import initialize_database
from shared.db.session import get_db_session
from shared.db.models.user import Role, Permission, RolePermission
from shared.auth.permissions import SYSTEM_PERMISSIONS, ROLE_PERMISSIONS_MAPPING
from shared.logging_config import get_logger

logger = get_logger("app.scripts.seed_rbac")

def seed_rbac():
    print("=========================================================")
    print(" CtrlBooks - RBAC Permissions & Roles Seeder")
    print("=========================================================")

    initialize_database()

    with get_db_session() as db:
        perm_map = {}
        for code, name, desc, module in SYSTEM_PERMISSIONS:
            perm = db.query(Permission).filter(Permission.code == code).first()
            if not perm:
                perm = Permission(code=code, name=name, description=desc, module=module)
                db.add(perm)
                db.flush()
                print(f"[+] Permission created: '{code}' ({name})")
            perm_map[code] = perm

        roles_config = [
            ("Admin", "ADMIN", "Full system administrator with unrestricted access", True),
            ("Operator", "OPERATOR", "Connector operator with data sync & pipeline management privileges", True),
            ("Viewer", "VIEWER", "Read-only viewer with dashboard & logs access", True),
        ]

        for name, code, desc, is_sys in roles_config:
            role = db.query(Role).filter(or_(Role.code == code, func.lower(Role.name) == name.lower())).first()
            if not role:
                role = Role(name=name, code=code, description=desc, is_system_role=is_sys)
                db.add(role)
                db.flush()
                print(f"[+] Role created: '{name}' (Code: {code})")
            else:
                role.name = name
                role.code = code
                role.description = desc
                role.is_system_role = is_sys
                db.flush()

            assigned_codes = ROLE_PERMISSIONS_MAPPING.get(code, [])
            for p_code in assigned_codes:
                perm_obj = perm_map.get(p_code)
                if perm_obj:
                    rp = db.query(RolePermission).filter(
                        RolePermission.role_id == role.id,
                        RolePermission.permission_id == perm_obj.id
                    ).first()
                    if not rp:
                        rp = RolePermission(role_id=role.id, permission_id=perm_obj.id)
                        db.add(rp)
                        db.flush()

        print("[+] RBAC permissions and system roles seeded successfully!\n")

if __name__ == "__main__":
    seed_rbac()
