from dataclasses import dataclass
from datetime import datetime, timezone
from typing import BinaryIO
from uuid import UUID

from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.domain_types import (
    AccessLevel,
    ProcessingStatus,
    PublicationStatus,
    ResourceAction,
    ScopeType,
    SourceStatus,
    SourceType,
)
from app.core.principal import Principal
from app.models.source import Source
from app.models.source_version import SourceVersion
from app.permissions.service import Capability, PermissionService, ResourceContext
from app.sources.errors import (
    DuplicateVersionError,
    InvalidFileError,
    InvalidSourceError,
    InvalidTransitionError,
    PermissionDeniedError,
    SourceNotFoundError,
)
from app.sources.file_validation import validate_file_signature, validate_upload_metadata
from app.storage.base import SavedObject, StorageAdapter
from app.storage.local import EmptyFileError, FileTooLargeError


@dataclass(frozen=True, slots=True)
class SourceCreate:
    title: str
    description: str | None
    source_type: SourceType
    business_scene: str | None
    scope_type: ScopeType
    department_id: UUID | None
    project_id: UUID | None
    owner_user_id: UUID | None
    access_level: AccessLevel


@dataclass(frozen=True, slots=True)
class VersionFile:
    version: SourceVersion
    stream: BinaryIO


class SourceService:
    def __init__(self, db: Session, permissions: PermissionService):
        self.db = db
        self.permissions = permissions

    def create_source(self, principal: Principal, data: SourceCreate) -> Source:
        title = data.title.strip()
        if not title:
            raise InvalidSourceError("Source title is required")
        owner_user_id = data.owner_user_id
        if data.scope_type is ScopeType.PERSONAL_DRAFT:
            if owner_user_id is not None and owner_user_id != principal.user_id:
                raise InvalidSourceError("Personal draft owner must be the current user")
            owner_user_id = principal.user_id
        self.validate_scope(
            data.scope_type, data.department_id, data.project_id, owner_user_id
        )
        resource = ResourceContext(
            scope_type=data.scope_type,
            access_level=data.access_level,
            department_id=data.department_id,
            owner_user_id=owner_user_id,
            project_id=data.project_id,
        )
        if not self.permissions.is_allowed(principal, ResourceAction.CREATE, resource):
            raise PermissionDeniedError("Source cannot be created in this scope")
        source = Source(
            title=title,
            description=data.description,
            source_type=data.source_type.value,
            business_scene=data.business_scene,
            scope_type=data.scope_type.value,
            department_id=data.department_id,
            project_id=data.project_id,
            owner_user_id=owner_user_id,
            access_level=data.access_level.value,
            status=SourceStatus.ACTIVE.value,
            created_by=principal.user_id,
        )
        self.db.add(source)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(source)
        return source

    def list_sources(
        self,
        principal: Principal,
        *,
        page: int,
        page_size: int,
        scope_type: ScopeType | None = None,
        department_id: UUID | None = None,
        source_type: SourceType | None = None,
        status: SourceStatus | None = None,
        business_scene: str | None = None,
        title: str | None = None,
    ) -> tuple[list[Source], int]:
        capabilities = self.permissions.capabilities_for(principal)
        visibility_filter = self.visibility_expression(principal, self.permissions)
        filters = [visibility_filter]
        requested_status = status or SourceStatus.ACTIVE
        if requested_status is SourceStatus.ARCHIVED and not capabilities.intersection(
            {Capability.PLATFORM_ADMIN, Capability.DEPARTMENT_ADMIN}
        ):
            filters.append(false())
        filters.append(Source.status == requested_status.value)
        if scope_type is not None:
            filters.append(Source.scope_type == scope_type.value)
        if department_id is not None:
            filters.append(Source.department_id == department_id)
        if source_type is not None:
            filters.append(Source.source_type == source_type.value)
        if business_scene is not None:
            filters.append(Source.business_scene == business_scene)
        if title:
            filters.append(Source.title.contains(title, autoescape=True))

        total = self.db.scalar(select(func.count()).select_from(Source).where(*filters)) or 0
        items = list(
            self.db.scalars(
                select(Source)
                .where(*filters)
                .order_by(Source.created_at.desc(), Source.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return items, total

    @staticmethod
    def visibility_expression(principal: Principal, permissions: PermissionService):
        capabilities = permissions.capabilities_for(principal)
        visibility = []
        if Capability.PLATFORM_ADMIN in capabilities:
            visibility.extend(
                [Source.scope_type == ScopeType.COMPANY.value,
                 Source.scope_type == ScopeType.DEPARTMENT.value]
            )
        elif Capability.DEPARTMENT_ADMIN in capabilities:
            visibility.extend(
                [
                    and_(
                        Source.scope_type == ScopeType.COMPANY.value,
                        Source.access_level == AccessLevel.INTERNAL.value,
                    ),
                    and_(
                        Source.scope_type == ScopeType.DEPARTMENT.value,
                        Source.department_id == principal.department_id,
                    ),
                ]
            )
        elif Capability.DEPARTMENT_USER in capabilities:
            visibility.extend(
                [
                    and_(
                        Source.scope_type == ScopeType.COMPANY.value,
                        Source.access_level == AccessLevel.INTERNAL.value,
                    ),
                    and_(
                        Source.scope_type == ScopeType.DEPARTMENT.value,
                        Source.department_id == principal.department_id,
                        Source.access_level == AccessLevel.INTERNAL.value,
                    ),
                ]
            )
        if capabilities:
            visibility.append(
                and_(
                    Source.scope_type == ScopeType.PERSONAL_DRAFT.value,
                    Source.owner_user_id == principal.user_id,
                )
            )

        return or_(*visibility) if visibility else false()

    def get_source(
        self, principal: Principal, source_id: UUID, action: ResourceAction = ResourceAction.READ
    ) -> Source:
        source = self.db.get(Source, source_id)
        if source is None or not self.permissions.is_allowed(
            principal, action, self.resource_for(source)
        ):
            raise SourceNotFoundError("Source not found")
        return source

    def archive_source(self, principal: Principal, source_id: UUID) -> Source:
        source = self.db.get(Source, source_id)
        if source is None:
            raise SourceNotFoundError("Source not found")
        action = (
            ResourceAction.UPDATE
            if source.scope_type == ScopeType.PERSONAL_DRAFT.value
            else ResourceAction.MANAGE
        )
        if not self.permissions.is_allowed(principal, action, self.resource_for(source)):
            raise SourceNotFoundError("Source not found")
        source.status = SourceStatus.ARCHIVED.value
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(source)
        return source

    @staticmethod
    def validate_scope(
        scope_type: ScopeType,
        department_id: UUID | None,
        project_id: UUID | None,
        owner_user_id: UUID | None,
    ) -> None:
        valid = {
            ScopeType.COMPANY: department_id is None and project_id is None,
            ScopeType.DEPARTMENT: department_id is not None and project_id is None,
            ScopeType.PERSONAL_DRAFT: owner_user_id is not None and project_id is None,
            ScopeType.PROJECT: project_id is not None,
        }[scope_type]
        if not valid:
            raise InvalidSourceError("Scope fields are invalid")

    @staticmethod
    def resource_for(source: Source) -> ResourceContext:
        return ResourceContext(
            scope_type=source.scope_type,
            access_level=source.access_level,
            department_id=source.department_id,
            owner_user_id=source.owner_user_id,
            project_id=source.project_id,
        )


class SourceVersionService:
    def __init__(
        self,
        db: Session,
        permissions: PermissionService,
        storage: StorageAdapter,
        max_upload_bytes: int,
    ):
        self.db = db
        self.permissions = permissions
        self.storage = storage
        self.max_upload_bytes = max_upload_bytes

    def upload_version(
        self,
        principal: Principal,
        source_id: UUID,
        stream: BinaryIO,
        original_filename: str | None,
        mime_type: str | None,
    ) -> SourceVersion:
        safe_filename = validate_upload_metadata(original_filename, mime_type)
        validate_file_signature(stream, safe_filename)
        saved: SavedObject | None = None
        try:
            saved = self.storage.save(stream, max_bytes=self.max_upload_bytes)
        except (EmptyFileError, FileTooLargeError) as exc:
            raise InvalidFileError(str(exc)) from exc

        try:
            source = self.db.scalar(
                select(Source).where(Source.id == source_id).with_for_update()
            )
            if source is None or not self.permissions.is_allowed(
                principal, ResourceAction.UPDATE, SourceService.resource_for(source)
            ):
                raise SourceNotFoundError("Source not found")
            if source.status != SourceStatus.ACTIVE.value:
                raise InvalidSourceError("Archived sources cannot receive versions")
            if source.source_type != SourceType.DOCUMENT.value:
                raise InvalidSourceError("File upload is only supported for DOCUMENT sources")
            duplicate = self.db.scalar(
                select(SourceVersion.id).where(
                    SourceVersion.source_id == source_id,
                    SourceVersion.file_hash == saved.file_hash,
                )
            )
            if duplicate is not None:
                raise DuplicateVersionError("This file already exists for the source")
            latest = self.db.scalar(
                select(func.max(SourceVersion.version_no)).where(
                    SourceVersion.source_id == source_id
                )
            )
            version = SourceVersion(
                source_id=source_id,
                version_no=(latest or 0) + 1,
                original_filename=safe_filename,
                mime_type=(mime_type or "application/octet-stream").split(";", 1)[0].lower(),
                file_size=saved.file_size,
                file_hash=saved.file_hash,
                storage_key=saved.storage_key,
                processing_status=ProcessingStatus.PENDING.value,
                publication_status=PublicationStatus.DRAFT.value,
                is_current=False,
                uploaded_by=principal.user_id,
            )
            self.db.add(version)
            self.db.commit()
            self.db.refresh(version)
            return version
        except (DuplicateVersionError, SourceNotFoundError, InvalidSourceError):
            self.db.rollback()
            self._cleanup_unreferenced(saved)
            raise
        except IntegrityError as exc:
            self.db.rollback()
            self._cleanup_unreferenced(saved)
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint in {"uq_source_versions_hash", "uq_source_versions_number"}:
                raise DuplicateVersionError(
                    "Version conflicts with an existing upload"
                ) from exc
            raise
        except Exception:
            self.db.rollback()
            self._cleanup_unreferenced(saved)
            raise

    def list_versions(self, principal: Principal, source_id: UUID) -> list[SourceVersion]:
        SourceService(self.db, self.permissions).get_source(principal, source_id)
        return list(
            self.db.scalars(
                select(SourceVersion)
                .where(SourceVersion.source_id == source_id)
                .order_by(SourceVersion.version_no.desc())
            ).all()
        )

    def get_version(self, principal: Principal, version_id: UUID) -> SourceVersion:
        version = self.db.get(SourceVersion, version_id)
        if version is None:
            raise SourceNotFoundError("Source version not found")
        SourceService(self.db, self.permissions).get_source(principal, version.source_id)
        return version

    def open_version_file(self, principal: Principal, version_id: UUID) -> VersionFile:
        version = self.get_version(principal, version_id)
        if not self.storage.exists(version.storage_key):
            raise SourceNotFoundError("Stored file not found")
        return VersionFile(version=version, stream=self.storage.open(version.storage_key))

    def publish_version(self, principal: Principal, version_id: UUID) -> SourceVersion:
        try:
            source_id = self.db.scalar(
                select(SourceVersion.source_id).where(SourceVersion.id == version_id)
            )
            if source_id is None:
                raise SourceNotFoundError("Source version not found")
            source = self.db.scalar(
                select(Source).where(Source.id == source_id).with_for_update()
            )
            if source is None or source.scope_type == ScopeType.PERSONAL_DRAFT.value:
                raise SourceNotFoundError("Source version not found")
            version = self.db.scalar(
                select(SourceVersion)
                .where(SourceVersion.id == version_id)
                .with_for_update()
            )
            if version is None or version.source_id != source.id:
                raise SourceNotFoundError("Source version not found")
            if not self.permissions.is_allowed(
                principal, ResourceAction.APPROVE, SourceService.resource_for(source)
            ):
                raise SourceNotFoundError("Source version not found")
            if source.status != SourceStatus.ACTIVE.value:
                raise InvalidTransitionError("Archived sources cannot publish versions")
            if (
                version.processing_status != ProcessingStatus.READY.value
                or version.publication_status != PublicationStatus.DRAFT.value
            ):
                raise InvalidTransitionError("Only READY + DRAFT versions can be published")
            now = datetime.now(timezone.utc)
            previous = self.db.scalar(
                select(SourceVersion)
                .where(
                    SourceVersion.source_id == source.id,
                    SourceVersion.is_current.is_(True),
                )
                .with_for_update()
            )
            if previous is not None and previous.id != version.id:
                previous.is_current = False
                previous.publication_status = PublicationStatus.SUPERSEDED.value
                previous.effective_to = now
            version.publication_status = PublicationStatus.PUBLISHED.value
            version.is_current = True
            version.effective_from = now
            version.effective_to = None
            version.published_by = principal.user_id
            version.published_at = now
            self.db.commit()
            self.db.refresh(version)
            return version
        except Exception:
            self.db.rollback()
            raise

    def withdraw_version(self, principal: Principal, version_id: UUID) -> SourceVersion:
        try:
            source_id = self.db.scalar(
                select(SourceVersion.source_id).where(SourceVersion.id == version_id)
            )
            if source_id is None:
                raise SourceNotFoundError("Source version not found")
            source = self.db.scalar(
                select(Source).where(Source.id == source_id).with_for_update()
            )
            if source is None or not self.permissions.is_allowed(
                principal, ResourceAction.APPROVE, SourceService.resource_for(source)
            ):
                raise SourceNotFoundError("Source version not found")
            version = self.db.scalar(
                select(SourceVersion)
                .where(SourceVersion.id == version_id)
                .with_for_update()
            )
            if version is None or version.source_id != source.id:
                raise SourceNotFoundError("Source version not found")
            if version.publication_status != PublicationStatus.PUBLISHED.value:
                raise InvalidTransitionError("Only published versions can be withdrawn")
            version.publication_status = PublicationStatus.WITHDRAWN.value
            version.is_current = False
            version.effective_to = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(version)
            return version
        except Exception:
            self.db.rollback()
            raise

    def mark_processing(self, version: SourceVersion) -> None:
        self._transition_processing(version, ProcessingStatus.PENDING, ProcessingStatus.PROCESSING)

    def mark_ready(self, version: SourceVersion) -> None:
        self._transition_processing(version, ProcessingStatus.PROCESSING, ProcessingStatus.READY)

    def mark_failed(self, version: SourceVersion, error_code: str) -> None:
        current = ProcessingStatus(version.processing_status)
        if current not in {ProcessingStatus.PENDING, ProcessingStatus.PROCESSING}:
            raise InvalidTransitionError("Version cannot transition to FAILED")
        version.processing_status = ProcessingStatus.FAILED.value
        version.processing_error_code = error_code
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _transition_processing(
        self, version: SourceVersion, expected: ProcessingStatus, target: ProcessingStatus
    ) -> None:
        if version.processing_status != expected.value:
            raise InvalidTransitionError(
                f"Expected {expected.value} before {target.value}"
            )
        version.processing_status = target.value
        version.processing_error_code = None
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _cleanup_unreferenced(self, saved: SavedObject | None) -> None:
        if saved is None or not saved.created:
            return
        try:
            references = self.db.scalar(
                select(func.count()).select_from(SourceVersion).where(
                    SourceVersion.storage_key == saved.storage_key
                )
            )
            if references == 0:
                self.storage.delete(saved.storage_key)
        except Exception:
            # Preserve the object if reference safety cannot be established.
            self.db.rollback()
