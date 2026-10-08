from uuid import UUID

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Response,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    decode_access_token,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    DepartmentResponse,
    LoginRequest,
    LoginResponse,
    RoleResponse,
    UserResponse,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


def build_user_response(user: User) -> UserResponse:
    department = None

    if user.department is not None:
        department = DepartmentResponse(
            id=user.department.id,
            code=user.department.code,
            name=user.department.name,
        )

    roles = [
        RoleResponse(
            code=role.code,
            name=role.name,
        )
        for role in user.roles
    ]

    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        department=department,
        roles=roles,
    )


def get_current_user(
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user_id = decode_access_token(access_token)

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    try:
        parsed_user_id = UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )

    query = (
        select(User)
        .options(
            selectinload(User.roles),
            selectinload(User.department),
        )
        .where(User.id == parsed_user_id)
    )

    user = db.scalar(query)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if user.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user


@router.post(
    "/login",
    response_model=LoginResponse,
)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:

    query = (
        select(User)
        .options(
            selectinload(User.roles),
            selectinload(User.department),
        )
        .where(User.email == payload.email.lower())
    )

    user = db.scalar(query)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(
        payload.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if user.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    token = create_access_token(
        subject=str(user.id)
    )

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=60 * 60,
        path="/",
    )

    return LoginResponse(
        message="Login successful",
        user=build_user_response(user),
    )


@router.get(
    "/me",
    response_model=UserResponse,
)
def me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return build_user_response(current_user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key="access_token",
        path="/",
    )

    return {
        "message": "Logout successful"
    }