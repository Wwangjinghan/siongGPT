from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.principal import Principal, get_current_principal
from app.ingestion.service import IngestionJobService
from app.permissions.service import PermissionService
from app.schemas.ingestion import IngestionJobActionResponse, IngestionJobResponse
from app.sources.errors import InvalidTransitionError, SourceNotFoundError


router = APIRouter(tags=["Ingestion"])


def get_ingestion_service(db: Session = Depends(get_db)) -> IngestionJobService:
    return IngestionJobService(
        db,
        PermissionService(),
        max_attempts=settings.ingestion_job_max_attempts,
        lease_seconds=settings.ingestion_job_lease_seconds,
        retry_base_seconds=settings.ingestion_retry_base_seconds,
    )


def handle_error(exc: Exception) -> None:
    if isinstance(exc, SourceNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, InvalidTransitionError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise exc


@router.post(
    "/source-versions/{version_id}/process",
    response_model=IngestionJobActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def process_version(
    version_id: UUID,
    principal: Principal = Depends(get_current_principal),
    service: IngestionJobService = Depends(get_ingestion_service),
):
    try:
        job, created = service.enqueue(principal, version_id)
        return IngestionJobActionResponse(job=job, created_new=created)
    except Exception as exc:
        handle_error(exc)


@router.post(
    "/source-versions/{version_id}/embeddings/reindex",
    response_model=IngestionJobActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def reindex_embeddings(
    version_id: UUID,
    principal: Principal = Depends(get_current_principal),
    service: IngestionJobService = Depends(get_ingestion_service),
):
    try:
        job, created = service.enqueue_embedding(principal, version_id)
        return IngestionJobActionResponse(job=job, created_new=created)
    except Exception as exc:
        handle_error(exc)


@router.get("/ingestion-jobs/{job_id}", response_model=IngestionJobResponse)
def get_job(
    job_id: UUID,
    principal: Principal = Depends(get_current_principal),
    service: IngestionJobService = Depends(get_ingestion_service),
):
    try:
        return service.get_for_principal(principal, job_id)
    except Exception as exc:
        handle_error(exc)


@router.post(
    "/ingestion-jobs/{job_id}/retry", response_model=IngestionJobActionResponse
)
def retry_job(
    job_id: UUID,
    principal: Principal = Depends(get_current_principal),
    service: IngestionJobService = Depends(get_ingestion_service),
):
    try:
        job, created = service.retry(principal, job_id)
        return IngestionJobActionResponse(job=job, created_new=created)
    except Exception as exc:
        handle_error(exc)


@router.post("/ingestion-jobs/{job_id}/cancel", response_model=IngestionJobResponse)
def cancel_job(
    job_id: UUID,
    principal: Principal = Depends(get_current_principal),
    service: IngestionJobService = Depends(get_ingestion_service),
):
    try:
        return service.cancel(principal, job_id)
    except Exception as exc:
        handle_error(exc)
