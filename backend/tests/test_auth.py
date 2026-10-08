import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import Response

from app.api.v1.auth import build_user_response, login, logout, me
from app.models.department import Department
from app.models.role import Role
from app.models.user import User
from app.schemas.auth import LoginRequest


class FakeSession:
    def __init__(self, user):
        self.user = user

    def scalar(self, _query):
        return self.user


class AuthRegressionTests(unittest.TestCase):
    def setUp(self):
        department = Department(id=uuid4(), code="FINANCE", name="Finance")
        self.user = User(
            id=uuid4(),
            email="user@example.com",
            password_hash="hash",
            display_name="Example User",
            status="ACTIVE",
            department_id=department.id,
        )
        self.user.department = department
        self.user.roles = [Role(id=uuid4(), code="EMPLOYEE", name="Employee")]

    @patch("app.api.v1.auth.create_access_token", return_value="signed-token")
    @patch("app.api.v1.auth.verify_password", return_value=True)
    def test_login_contract_and_cookie_remain_intact(self, _verify, _token):
        response = Response()
        result = login(
            LoginRequest(email="USER@EXAMPLE.COM", password="secret"),
            response,
            FakeSession(self.user),
        )

        self.assertEqual(result.message, "Login successful")
        cookie = response.headers["set-cookie"]
        self.assertIn("access_token=signed-token", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)

    def test_me_reuses_existing_user_response(self):
        self.assertEqual(me(self.user), build_user_response(self.user))

    def test_logout_expires_existing_cookie(self):
        response = Response()
        self.assertEqual(logout(response), {"message": "Logout successful"})
        cookie = response.headers["set-cookie"]
        self.assertIn("access_token=", cookie)
        self.assertIn("Max-Age=0", cookie)
