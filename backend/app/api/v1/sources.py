from functools import lru_cache
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.domain_types import ScopeType, SourceStatus, SourceType
from app.core.principal import Principal, get_current_principal
from app.permissions.service import PermissionService
from app.schemas.source import (
    SourceCreateRequest,
    SourcePageResponse,
    SourceResponse,
    SourceVersionResponse,
)
from app.sources.errors import (
    DuplicateVersionError,
    InvalidFileError,
    InvalidSourceError,
    InvalidTransitionError,
    PermissionDeniedError,
    SourceNotFoundError,
)
from app.sources.services import SourceCreate, SourceService, SourceVersionService
from app.storage.local import LocalStorageAdapter


router = APIRouter(tags=["Sources"])


@lru_cache
def get_storage() -> LocalStorageAdapter:
    return LocalStorageAdapter(settings.source_storage_root)


def get_permissions() -> PermissionService:
    return PermissionService()


def get_source_service(
    db: Session = Depends(get_db),
    permissions: PermissionService = Depends(get_permissions),
) -> SourceService:
    return SourceService(db, permissions)


def get_version_service(
    db: Session = Depends(get_db),
    permissions: PermissionService = Depends(get_permissions),
    storage: LocalStorageAdapter = Depends(get_storage),
) -> SourceVersionService:
    return SourceVersionService(
        db, permissions, storage, settings.source_max_upload_bytes
    )


def raise_http_error(exc: Exception) -> None:
    if isinstance(exc, SourceNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, PermissionDeniedError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, DuplicateVersionError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, InvalidTransitionError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, (InvalidSourceError, InvalidFileError)):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


@router.post(
    "/sources", response_model=SourceResponse, status_code=status.HTTP_201_CREATED
)
def create_source(
    payload: SourceCreateRequest,
    principal: Principal = Depends(get_current_principal),
    service: SourceService = Depends(get_source_service),
):
    try:
        return service.create_source(
            principal,
            SourceCreate(
                title=payload.title,
                description=payload.description,
                source_type=payload.source_type,
                business_scene=payload.business_scene,
                scope_type=payload.scope_type,
                department_id=payload.department_id,
                project_id=payload.project_id,
                owner_user_id=payload.owner_user_id,
                access_level=payload.access_level,
            ),
        )
    except Exception as exc:
        raise_http_error(exc)


@router.get("/sources", response_model=SourcePageResponse)
def list_sources(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    scope_type: ScopeType | None = None,
    department_id: UUID | None = None,
    source_type: SourceType | None = None,
    source_status: SourceStatus | None = Query(default=None, alias="status"),
    business_scene: str | None = None,
    title: str | None = None,
    principal: Principal = Depends(get_current_principal),
    service: SourceService = Depends(get_source_service),
):
    items, total = service.list_sources(
        principal,
        page=page,
        page_size=page_size,
        scope_type=scope_type,
        department_id=department_id,
        source_type=source_type,
        status=source_status,
        business_scene=business_scene,
        title=title,
    )
    return SourcePageResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/sources/{source_id}", response_model=SourceResponse)
def get_source(
    source_id: UUID,
    principal: Principal = Depends(get_current_principal),
    service: SourceService = Depends(get_source_service),
):
    try:
        return service.get_source(principal, source_id)
    except Exception as exc:
        raise_http_error(exc)


@router.post("/sources/{source_id}/archive", response_model=SourceResponse)
def archive_source(
    source_id: UUID,
    principal: Principal = Depends(get_current_principal),
    service: SourceService = Depends(get_source_service),
):
    try:
        return service.archive_source(principal, source_id)
    except Exception as exc:
        raise_http_error(exc)


@router.post(
    "/sources/{source_id}/versions",
    response_model=SourceVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_version(
    source_id: UUID,
    file: UploadFile = File(...),
    principal: Principal = Depends(get_current_principal),
    service: SourceVersionService = Depends(get_version_service),
):
    try:
        return service.upload_version(
            principal, source_id, file.file, file.filename, file.content_type
        )
    except Exception as exc:
        raise_http_error(exc)


@router.get(
    "/sources/{source_id}/versions", response_model=list[SourceVersionResponse]
)
def list_versions(
    source_id: UUID,
    principal: Principal = Depends(get_current_principal),
    service: SourceVersionService = Depends(get_version_service),
):
    try:
        return service.list_versions(principal, source_id)
    except Exception as exc:
        raise_http_error(exc)


@router.get("/source-versions/{version_id}", response_model=SourceVersionResponse)
def get_version(
    version_id: UUID,
    principal: Principal = Depends(get_current_principal),
    service: SourceVersionService = Depends(get_version_service),
):
    try:
        return service.get_version(principal, version_id)
    except Exception as exc:
        raise_http_error(exc)


@router.get("/source-versions/{version_id}/download")
def download_version(
    version_id: UUID,
    principal: Principal = Depends(get_current_principal),
    service: SourceVersionService = Depends(get_version_service),
):
    try:
        opened = service.open_version_file(principal, version_id)
    except Exception as exc:
        raise_http_error(exc)

    def chunks():
        try:
            while chunk := opened.stream.read(1024 * 1024):
                yield chunk
        finally:
            opened.stream.close()

    filename = quote(opened.version.original_filename, safe="")
    return StreamingResponse(
        chunks(),
        media_type=opened.version.mime_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/source-versions/{version_id}/publish", response_model=SourceVersionResponse)
def publish_version(
    version_id: UUID,
    principal: Principal = Depends(get_current_principal),
    service: SourceVersionService = Depends(get_version_service),
):
    try:
        return service.publish_version(principal, version_id)
    except Exception as exc:
        raise_http_error(exc)


@router.post("/source-versions/{version_id}/withdraw", response_model=SourceVersionResponse)
def withdraw_version(
    version_id: UUID,
    principal: Principal = Depends(get_current_principal),
    service: SourceVersionService = Depends(get_version_service),
):
    try:
        return service.withdraw_version(principal, version_id)
    except Exception as exc:
        raise_http_error(exc)
