from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends

from app.api.v1.auth import get_current_user
from app.models.user import User


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    department_id: UUID | None
    roles: frozenset[str]
    authenticated: bool
    active: bool

    @classmethod
    def from_user(cls, user: User) -> "Principal":
        return cls(
            user_id=user.id,
            department_id=user.department_id,
            roles=frozenset(role.code for role in user.roles),
            authenticated=True,
            active=user.status == "ACTIVE",
        )


def get_current_principal(
    current_user: User = Depends(get_current_user),
) -> Principal:
    """Adapt the existing database-backed Auth dependency for authorization."""

    return Principal.from_user(current_user)
