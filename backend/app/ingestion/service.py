from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.domain_types import (
    IngestionErrorCode,
    IngestionJobStatus,
    IngestionJobType,
    ProcessingStatus,
    PublicationStatus,
    ResourceAction,
    SourceStatus,
)
from app.core.principal import Principal
from app.models.ingestion_job import IngestionJob
from app.models.source import Source
from app.models.source_version import SourceVersion
from app.permissions.service import PermissionService
from app.sources.errors import InvalidTransitionError, SourceNotFoundError
from app.sources.services import SourceService


class LeaseLostError(Exception):
    pass


class IngestionJobService:
    def __init__(
        self,
        db: Session,
        permissions: PermissionService,
        *,
        max_attempts: int,
        lease_seconds: int,
        retry_base_seconds: int,
    ):
        self.db = db
        self.permissions = permissions
        self.max_attempts = max_attempts
        self.lease_seconds = lease_seconds
        self.retry_base_seconds = retry_base_seconds

    def enqueue(self, principal: Principal, version_id: UUID) -> tuple[IngestionJob, bool]:
        version, source = self._locked_version_source(version_id)
        self._authorize(principal, source, ResourceAction.UPDATE)
        if source.status != SourceStatus.ACTIVE.value:
            raise InvalidTransitionError("Archived sources cannot be processed")
        if (
            version.processing_status != ProcessingStatus.PENDING.value
            or version.publication_status != PublicationStatus.DRAFT.value
            or version.is_current
        ):
            raise InvalidTransitionError("Source version is not eligible for processing")
        existing = self.db.scalar(
            select(IngestionJob).where(
                IngestionJob.source_version_id == version_id,
                IngestionJob.status.in_(
                    [IngestionJobStatus.QUEUED.value, IngestionJobStatus.RUNNING.value]
                ),
            )
        )
        if existing is not None:
            self.db.commit()
            return existing, False
        now = datetime.now(timezone.utc)
        job = IngestionJob(
            source_version_id=version_id,
            job_type=IngestionJobType.DOCUMENT_INGESTION.value,
            status=IngestionJobStatus.QUEUED.value,
            attempt_count=0,
            max_attempts=self.max_attempts,
            available_at=now,
            created_by=principal.user_id,
        )
        self.db.add(job)
        try:
            self.db.commit()
            self.db.refresh(job)
            return job, True
        except IntegrityError:
            self.db.rollback()
            existing = self.db.scalar(
                select(IngestionJob).where(
                    IngestionJob.source_version_id == version_id,
                    IngestionJob.status.in_(
                        [IngestionJobStatus.QUEUED.value, IngestionJobStatus.RUNNING.value]
                    ),
                )
            )
            if existing is not None:
                return existing, False
            raise

    def enqueue_embedding(self, principal: Principal, version_id: UUID) -> tuple[IngestionJob, bool]:
        version, source = self._locked_version_source(version_id)
        allowed = self.permissions.is_allowed(
            principal, ResourceAction.APPROVE, SourceService.resource_for(source)
        ) or self.permissions.is_allowed(
            principal, ResourceAction.MANAGE, SourceService.resource_for(source)
        )
        if not allowed:
            raise SourceNotFoundError("Source version not found")
        if source.status != SourceStatus.ACTIVE.value or version.processing_status != ProcessingStatus.READY.value:
            raise InvalidTransitionError("Only READY versions on active sources can be reindexed")
        existing = self.db.scalar(
            select(IngestionJob).where(
                IngestionJob.source_version_id == version_id,
                IngestionJob.status.in_([IngestionJobStatus.QUEUED.value, IngestionJobStatus.RUNNING.value]),
            )
        )
        if existing is not None:
            self.db.commit()
            return existing, False
        job = IngestionJob(
            source_version_id=version_id,
            job_type=IngestionJobType.DOCUMENT_EMBEDDING.value,
            status=IngestionJobStatus.QUEUED.value,
            attempt_count=0,
            max_attempts=self.max_attempts,
            available_at=datetime.now(timezone.utc),
            created_by=principal.user_id,
        )
        self.db.add(job)
        try:
            self.db.commit()
            self.db.refresh(job)
            return job, True
        except IntegrityError:
            self.db.rollback()
            existing = self.db.scalar(
                select(IngestionJob).where(
                    IngestionJob.source_version_id == version_id,
                    IngestionJob.status.in_([IngestionJobStatus.QUEUED.value, IngestionJobStatus.RUNNING.value]),
                )
            )
            if existing is not None:
                return existing, False
            raise

    def get_for_principal(self, principal: Principal, job_id: UUID) -> IngestionJob:
        job = self.db.get(IngestionJob, job_id)
        if job is None:
            raise SourceNotFoundError("Ingestion job not found")
        version = self.db.get(SourceVersion, job.source_version_id)
        source = self.db.get(Source, version.source_id) if version else None
        if source is None or not self.permissions.is_allowed(
            principal, ResourceAction.READ, SourceService.resource_for(source)
        ):
            raise SourceNotFoundError("Ingestion job not found")
        return job

    def retry(self, principal: Principal, job_id: UUID) -> tuple[IngestionJob, bool]:
        job = self.db.scalar(
            select(IngestionJob).where(IngestionJob.id == job_id).with_for_update()
        )
        if job is None:
            raise SourceNotFoundError("Ingestion job not found")
        version = self.db.get(SourceVersion, job.source_version_id)
        source = self.db.get(Source, version.source_id) if version else None
        self._authorize_job_change(principal, source, job)
        if job.status == IngestionJobStatus.FAILED.value and job.attempt_count < job.max_attempts:
            job.status = IngestionJobStatus.QUEUED.value
            job.available_at = datetime.now(timezone.utc)
            job.lease_owner = None
            job.lease_expires_at = None
            self.db.commit()
            self.db.refresh(job)
            return job, False
        if job.status == IngestionJobStatus.DEAD_LETTER.value:
            active = self.db.scalar(
                select(IngestionJob).where(
                    IngestionJob.source_version_id == job.source_version_id,
                    IngestionJob.status.in_(
                        [IngestionJobStatus.QUEUED.value, IngestionJobStatus.RUNNING.value]
                    ),
                )
            )
            if active is not None:
                self.db.commit()
                return active, False
            replacement = IngestionJob(
                source_version_id=job.source_version_id,
                job_type=job.job_type,
                status=IngestionJobStatus.QUEUED.value,
                attempt_count=0,
                max_attempts=self.max_attempts,
                available_at=datetime.now(timezone.utc),
                created_by=principal.user_id,
            )
            self.db.add(replacement)
            self.db.commit()
            self.db.refresh(replacement)
            return replacement, True
        raise InvalidTransitionError("Only failed jobs can be retried")

    def cancel(self, principal: Principal, job_id: UUID) -> IngestionJob:
        job = self.db.scalar(
            select(IngestionJob).where(IngestionJob.id == job_id).with_for_update()
        )
        if job is None:
            raise SourceNotFoundError("Ingestion job not found")
        version = self.db.get(SourceVersion, job.source_version_id)
        source = self.db.get(Source, version.source_id) if version else None
        self._authorize_job_change(principal, source, job)
        if job.status != IngestionJobStatus.QUEUED.value:
            raise InvalidTransitionError("Only queued jobs can be cancelled")
        job.status = IngestionJobStatus.CANCELLED.value
        job.finished_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        return job

    def claim_next(self, worker_id: str) -> IngestionJob | None:
        now = datetime.now(timezone.utc)
        self._recover_expired_locked(now)
        self._requeue_failed_locked(now)
        job = self.db.scalar(
            select(IngestionJob)
            .where(
                IngestionJob.status == IngestionJobStatus.QUEUED.value,
                IngestionJob.available_at <= now,
                IngestionJob.attempt_count < IngestionJob.max_attempts,
            )
            .order_by(IngestionJob.available_at, IngestionJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            self.db.commit()
            return None
        job.status = IngestionJobStatus.RUNNING.value
        job.attempt_count += 1
        job.lease_owner = worker_id
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
        job.started_at = job.started_at or now
        job.finished_at = None
        self.db.commit()
        self.db.refresh(job)
        return job

    def heartbeat(self, job_id: UUID, worker_id: str) -> bool:
        now = datetime.now(timezone.utc)
        result = self.db.execute(
            update(IngestionJob)
            .where(
                IngestionJob.id == job_id,
                IngestionJob.status == IngestionJobStatus.RUNNING.value,
                IngestionJob.lease_owner == worker_id,
                IngestionJob.lease_expires_at > now,
            )
            .values(
                heartbeat_at=now,
                lease_expires_at=now + timedelta(seconds=self.lease_seconds),
            )
        )
        self.db.commit()
        return result.rowcount == 1

    def lock_owned_running_job(self, job_id: UUID, worker_id: str) -> IngestionJob:
        now = datetime.now(timezone.utc)
        job = self.db.scalar(
            select(IngestionJob)
            .where(
                IngestionJob.id == job_id,
                IngestionJob.status == IngestionJobStatus.RUNNING.value,
                IngestionJob.lease_owner == worker_id,
                IngestionJob.lease_expires_at > now,
            )
            .with_for_update()
        )
        if job is None:
            raise LeaseLostError("Worker lease is no longer valid")
        return job

    def fail_owned_job(
        self,
        job_id: UUID,
        worker_id: str,
        code: IngestionErrorCode,
        message: str,
        *,
        affect_version: bool = True,
    ) -> bool:
        try:
            job = self.lock_owned_running_job(job_id, worker_id)
        except LeaseLostError:
            self.db.rollback()
            return False
        now = datetime.now(timezone.utc)
        version = self.db.get(SourceVersion, job.source_version_id)
        if affect_version and version is not None:
            version.processing_status = ProcessingStatus.FAILED.value
            version.processing_error_code = code.value
        job.status = (
            IngestionJobStatus.DEAD_LETTER.value
            if job.attempt_count >= job.max_attempts
            else IngestionJobStatus.FAILED.value
        )
        job.available_at = now + timedelta(
            seconds=self.retry_base_seconds * (2 ** max(job.attempt_count - 1, 0))
        )
        job.error_code = code.value
        job.error_message = message[:500]
        job.finished_at = now
        job.lease_owner = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        self.db.commit()
        return True

    def _recover_expired_locked(self, now: datetime) -> None:
        jobs = list(
            self.db.scalars(
                select(IngestionJob)
                .where(
                    IngestionJob.status == IngestionJobStatus.RUNNING.value,
                    IngestionJob.lease_expires_at <= now,
                )
                .with_for_update(skip_locked=True)
            ).all()
        )
        for job in jobs:
            job.status = (
                IngestionJobStatus.DEAD_LETTER.value
                if job.attempt_count >= job.max_attempts
                else IngestionJobStatus.QUEUED.value
            )
            job.available_at = now
            job.lease_owner = None
            job.lease_expires_at = None
            job.heartbeat_at = None
            if job.status == IngestionJobStatus.DEAD_LETTER.value:
                job.finished_at = now
                job.error_code = IngestionErrorCode.LEASE_LOST.value
                job.error_message = "Worker lease expired after maximum attempts"
                version = self.db.get(SourceVersion, job.source_version_id)
                if version is not None and job.job_type == IngestionJobType.DOCUMENT_INGESTION.value:
                    version.processing_status = ProcessingStatus.FAILED.value
                    version.processing_error_code = IngestionErrorCode.LEASE_LOST.value

    def _requeue_failed_locked(self, now: datetime) -> None:
        jobs = list(
            self.db.scalars(
                select(IngestionJob)
                .where(
                    IngestionJob.status == IngestionJobStatus.FAILED.value,
                    IngestionJob.available_at <= now,
                    IngestionJob.attempt_count < IngestionJob.max_attempts,
                )
                .with_for_update(skip_locked=True)
            ).all()
        )
        for job in jobs:
            job.status = IngestionJobStatus.QUEUED.value

    def _locked_version_source(self, version_id: UUID) -> tuple[SourceVersion, Source]:
        source_id = self.db.scalar(
            select(SourceVersion.source_id).where(SourceVersion.id == version_id)
        )
        if source_id is None:
            raise SourceNotFoundError("Source version not found")
        source = self.db.scalar(
            select(Source).where(Source.id == source_id).with_for_update()
        )
        version = self.db.scalar(
            select(SourceVersion)
            .where(SourceVersion.id == version_id)
            .with_for_update()
        )
        if source is None or version is None:
            raise SourceNotFoundError("Source version not found")
        return version, source

    def _authorize(
        self, principal: Principal, source: Source | None, action: ResourceAction
    ) -> None:
        if source is None or not self.permissions.is_allowed(
            principal, action, SourceService.resource_for(source)
        ):
            raise SourceNotFoundError("Ingestion job not found")

    def _authorize_job_change(
        self, principal: Principal, source: Source | None, job: IngestionJob
    ) -> None:
        if job.job_type != IngestionJobType.DOCUMENT_EMBEDDING.value:
            self._authorize(principal, source, ResourceAction.UPDATE)
            return
        if source is None:
            raise SourceNotFoundError("Ingestion job not found")
        resource = SourceService.resource_for(source)
        if not (
            self.permissions.is_allowed(principal, ResourceAction.APPROVE, resource)
            or self.permissions.is_allowed(principal, ResourceAction.MANAGE, resource)
        ):
            raise SourceNotFoundError("Ingestion job not found")
