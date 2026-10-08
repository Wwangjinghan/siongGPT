from uuid import UUID

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class RoleResponse(BaseModel):
    code: str
    name: str


class DepartmentResponse(BaseModel):
    id: UUID
    code: str
    name: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    status: str
    department: DepartmentResponse | None
    roles: list[RoleResponse]


class LoginResponse(BaseModel):
    message: str
    user: UserResponse