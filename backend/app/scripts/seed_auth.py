from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.department import Department
from app.models.role import Role
from app.models.user import User


DEFAULT_PASSWORD = "SiongTest123!"


def get_or_create_department(db) -> Department:
    department = db.scalar(
        select(Department).where(Department.code == "FINANCE")
    )

    if department is None:
        department = Department(
            code="FINANCE",
            name="Finance",
        )
        db.add(department)
        db.flush()

    return department


def get_or_create_roles(db) -> dict[str, Role]:
    role_definitions = {
        "SYSTEM_ADMIN": "System Administrator",
        "FINANCE_ADMIN": "Finance Administrator",
        "EMPLOYEE": "Employee",
    }

    roles: dict[str, Role] = {}

    for code, name in role_definitions.items():
        role = db.scalar(
            select(Role).where(Role.code == code)
        )

        if role is None:
            role = Role(
                code=code,
                name=name,
            )
            db.add(role)
            db.flush()

        roles[code] = role

    return roles


def create_user_if_not_exists(
    db,
    *,
    email: str,
    display_name: str,
    department: Department,
    role: Role,
) -> None:
    existing_user = db.scalar(
        select(User).where(User.email == email)
    )

    if existing_user is not None:
        print(f"User already exists, skipping: {email}")
        return

    user = User(
        email=email,
        display_name=display_name,
        password_hash=hash_password(DEFAULT_PASSWORD),
        department_id=department.id,
        status="ACTIVE",
    )

    user.roles.append(role)

    db.add(user)

    print(f"Created user: {email}")


def seed() -> None:
    db = SessionLocal()

    try:
        finance_department = get_or_create_department(db)
        roles = get_or_create_roles(db)

        create_user_if_not_exists(
            db,
            email="admin@siong.local",
            display_name="System Admin",
            department=finance_department,
            role=roles["SYSTEM_ADMIN"],
        )

        create_user_if_not_exists(
            db,
            email="finance@siong.local",
            display_name="Finance User",
            department=finance_department,
            role=roles["FINANCE_ADMIN"],
        )

        create_user_if_not_exists(
            db,
            email="employee@siong.local",
            display_name="General Employee",
            department=finance_department,
            role=roles["EMPLOYEE"],
        )

        db.commit()

        print()
        print("Seed completed successfully.")
        print("Local development accounts:")
        print("  admin@siong.local")
        print("  finance@siong.local")
        print("  employee@siong.local")
        print(f"Default password: {DEFAULT_PASSWORD}")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed()