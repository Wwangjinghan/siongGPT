from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from uuid import UUID

from app.core.domain_types import AccessLevel, ResourceAction, ScopeType
from app.core.principal import Principal


class Capability(str, Enum):
    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    DEPARTMENT_ADMIN = "DEPARTMENT_ADMIN"
    DEPARTMENT_USER = "DEPARTMENT_USER"


# This is the single V1 authority for translating existing role codes into platform
# capabilities. It can later be replaced by database configuration without changing
# routers or callers of PermissionService.
ROLE_CAPABILITIES = MappingProxyType(
    {
        "SYSTEM_ADMIN": frozenset({Capability.PLATFORM_ADMIN}),
        "DEPARTMENT_ADMIN": frozenset({Capability.DEPARTMENT_ADMIN}),
        "FINANCE_ADMIN": frozenset({Capability.DEPARTMENT_ADMIN}),
        "FINANCE_USER": frozenset({Capability.DEPARTMENT_USER}),
        "EMPLOYEE": frozenset({Capability.DEPARTMENT_USER}),
    }
)


@dataclass(frozen=True, slots=True)
class ResourceContext:
    scope_type: ScopeType | str | None
    access_level: AccessLevel | str | None
    department_id: UUID | None = None
    owner_user_id: UUID | None = None
    project_id: UUID | None = None


class PermissionService:
    """Central, fail-closed authorization for platform resources."""

    def is_allowed(
        self,
        principal: Principal,
        action: ResourceAction | str | None,
        resource: ResourceContext,
    ) -> bool:
        if not principal.authenticated or not principal.active:
            return False

        parsed_action = self._parse(ResourceAction, action)
        scope = self._parse(ScopeType, resource.scope_type)
        access_level = self._parse(AccessLevel, resource.access_level)
        if parsed_action is None or scope is None or access_level is None:
            return False
        if not self._has_required_scope_fields(scope, resource):
            return False

        capabilities = self._capabilities_for(principal)
        if not capabilities:
            return False

        # Project membership has no trusted resolver in V1, so every request fails.
        if scope is ScopeType.PROJECT:
            return False

        # Personal drafts never inherit administrator access in V1.
        if scope is ScopeType.PERSONAL_DRAFT:
            return (
                resource.owner_user_id == principal.user_id
                and parsed_action
                in {
                    ResourceAction.READ,
                    ResourceAction.CREATE,
                    ResourceAction.UPDATE,
                }
            )

        if Capability.PLATFORM_ADMIN in capabilities:
            return True

        if scope is ScopeType.COMPANY:
            return (
                parsed_action is ResourceAction.READ
                and access_level is AccessLevel.INTERNAL
                and bool(capabilities)
            )

        same_department = (
            principal.department_id is not None
            and resource.department_id == principal.department_id
        )
        if not same_department:
            return False

        if Capability.DEPARTMENT_ADMIN in capabilities:
            return True

        return (
            Capability.DEPARTMENT_USER in capabilities
            and parsed_action is ResourceAction.READ
            and access_level is AccessLevel.INTERNAL
        )

    @staticmethod
    def _parse(enum_type, value):
        try:
            return enum_type(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _capabilities_for(principal: Principal) -> frozenset[Capability]:
        if not principal.roles:
            return frozenset()
        capabilities: set[Capability] = set()
        for role in principal.roles:
            mapped = ROLE_CAPABILITIES.get(role)
            if mapped is None:
                return frozenset()
            capabilities.update(mapped)
        if Capability.PLATFORM_ADMIN in capabilities and len(capabilities) > 1:
            return frozenset()
        return frozenset(capabilities)

    def capabilities_for(self, principal: Principal) -> frozenset[Capability]:
        if not principal.authenticated or not principal.active:
            return frozenset()
        return self._capabilities_for(principal)

    @staticmethod
    def _has_required_scope_fields(
        scope: ScopeType,
        resource: ResourceContext,
    ) -> bool:
        if scope is ScopeType.COMPANY:
            return resource.department_id is None and resource.project_id is None
        if scope is ScopeType.DEPARTMENT:
            return resource.department_id is not None and resource.project_id is None
        if scope is ScopeType.PERSONAL_DRAFT:
            return resource.owner_user_id is not None and resource.project_id is None
        if scope is ScopeType.PROJECT:
            return resource.project_id is not None
        return False
