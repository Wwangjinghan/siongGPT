import unittest
from uuid import uuid4

from app.core.principal import Principal
from app.models.department import Department
from app.models.role import Role
from app.models.user import User


class PrincipalTests(unittest.TestCase):
    def test_principal_reuses_database_user_department_and_roles(self):
        department = Department(id=uuid4(), code="FINANCE", name="Finance")
        user = User(
            id=uuid4(),
            email="user@example.com",
            password_hash="unused",
            display_name="User",
            status="ACTIVE",
            department_id=department.id,
        )
        user.roles = [
            Role(id=uuid4(), code="FINANCE_USER", name="Finance User"),
            Role(id=uuid4(), code="EMPLOYEE", name="Employee"),
        ]

        principal = Principal.from_user(user)

        self.assertEqual(principal.user_id, user.id)
        self.assertEqual(principal.department_id, department.id)
        self.assertEqual(principal.roles, frozenset({"FINANCE_USER", "EMPLOYEE"}))
        self.assertTrue(principal.authenticated)
        self.assertTrue(principal.active)
