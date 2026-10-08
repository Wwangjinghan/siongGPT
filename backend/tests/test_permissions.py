import unittest
from uuid import uuid4

from app.core.domain_types import AccessLevel, ResourceAction, ScopeType
from app.core.principal import Principal
from app.permissions.service import PermissionService, ResourceContext


class PermissionServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = PermissionService()
        self.user_id = uuid4()
        self.department_id = uuid4()

    def principal(self, *roles, department_id=None, user_id=None):
        return Principal(
            user_id=user_id or self.user_id,
            department_id=department_id or self.department_id,
            roles=frozenset(roles),
            authenticated=True,
            active=True,
        )

    def resource(self, scope, access=AccessLevel.INTERNAL, **kwargs):
        return ResourceContext(scope_type=scope, access_level=access, **kwargs)

    def test_system_admin_can_manage_company_and_departments(self):
        admin = self.principal("SYSTEM_ADMIN")
        self.assertTrue(
            self.service.is_allowed(
                admin,
                ResourceAction.MANAGE,
                self.resource(ScopeType.COMPANY, AccessLevel.CONFIDENTIAL),
            )
        )
        self.assertTrue(
            self.service.is_allowed(
                admin,
                ResourceAction.APPROVE,
                self.resource(
                    ScopeType.DEPARTMENT,
                    AccessLevel.CONFIDENTIAL,
                    department_id=uuid4(),
                ),
            )
        )

    def test_system_admin_does_not_bypass_personal_owner_boundary(self):
        self.assertFalse(
            self.service.is_allowed(
                self.principal("SYSTEM_ADMIN"),
                ResourceAction.READ,
                self.resource(
                    ScopeType.PERSONAL_DRAFT,
                    owner_user_id=uuid4(),
                ),
            )
        )

    def test_department_admin_cannot_access_other_department_restricted(self):
        self.assertFalse(
            self.service.is_allowed(
                self.principal("FINANCE_ADMIN"),
                ResourceAction.READ,
                self.resource(
                    ScopeType.DEPARTMENT,
                    AccessLevel.RESTRICTED,
                    department_id=uuid4(),
                ),
            )
        )

    def test_department_admin_mapping_is_not_based_on_admin_suffix(self):
        resource = self.resource(
            ScopeType.DEPARTMENT,
            department_id=self.department_id,
        )
        self.assertTrue(
            self.service.is_allowed(
                self.principal("DEPARTMENT_ADMIN"), ResourceAction.MANAGE, resource
            )
        )
        self.assertFalse(
            self.service.is_allowed(
                self.principal("MADE_UP_ADMIN"), ResourceAction.MANAGE, resource
            )
        )

    def test_department_user_can_only_read_same_department_internal(self):
        user = self.principal("EMPLOYEE")
        resource = self.resource(
            ScopeType.DEPARTMENT,
            department_id=self.department_id,
        )
        self.assertTrue(self.service.is_allowed(user, ResourceAction.READ, resource))
        for action in (
            ResourceAction.REVIEW,
            ResourceAction.APPROVE,
            ResourceAction.MANAGE,
        ):
            self.assertFalse(self.service.is_allowed(user, action, resource))

    def test_personal_draft_is_owner_only(self):
        owner_resource = self.resource(
            ScopeType.PERSONAL_DRAFT,
            AccessLevel.CONFIDENTIAL,
            owner_user_id=self.user_id,
        )
        self.assertTrue(
            self.service.is_allowed(
                self.principal("EMPLOYEE"), ResourceAction.UPDATE, owner_resource
            )
        )
        self.assertFalse(
            self.service.is_allowed(
                self.principal("FINANCE_ADMIN", user_id=uuid4()),
                ResourceAction.READ,
                owner_resource,
            )
        )

    def test_personal_draft_requires_a_supported_role(self):
        resource = self.resource(
            ScopeType.PERSONAL_DRAFT,
            owner_user_id=self.user_id,
        )
        for roles in (
            (),
            ("UNKNOWN_ROLE",),
            ("UNKNOWN_ADMIN", "OTHER"),
            ("EMPLOYEE", "UNKNOWN_ROLE"),
            ("SYSTEM_ADMIN", "EMPLOYEE"),
        ):
            with self.subTest(roles=roles):
                self.assertFalse(
                    self.service.is_allowed(
                        self.principal(*roles), ResourceAction.UPDATE, resource
                    )
                )

    def test_supported_roles_can_update_their_own_personal_draft(self):
        resource = self.resource(
            ScopeType.PERSONAL_DRAFT,
            owner_user_id=self.user_id,
        )
        for role in ("SYSTEM_ADMIN", "DEPARTMENT_ADMIN", "FINANCE_USER", "EMPLOYEE"):
            with self.subTest(role=role):
                self.assertTrue(
                    self.service.is_allowed(
                        self.principal(role), ResourceAction.UPDATE, resource
                    )
                )

    def test_project_scope_denies_without_membership_resolver(self):
        self.assertFalse(
            self.service.is_allowed(
                self.principal("SYSTEM_ADMIN"),
                ResourceAction.READ,
                self.resource(ScopeType.PROJECT, project_id=uuid4()),
            )
        )

    def test_malformed_or_incomplete_context_denies(self):
        user = self.principal("SYSTEM_ADMIN")
        cases = (
            self.resource(None),
            self.resource(ScopeType.DEPARTMENT),
            self.resource(ScopeType.COMPANY, access="TOP_SECRET"),
        )
        for resource in cases:
            with self.subTest(resource=resource):
                self.assertFalse(
                    self.service.is_allowed(user, ResourceAction.READ, resource)
                )

    def test_untrusted_extra_input_cannot_expand_permissions(self):
        resource = self.resource(
            ScopeType.DEPARTMENT,
            AccessLevel.CONFIDENTIAL,
            department_id=uuid4(),
        )
        llm_output = {"grant_access": True, "roles": ["SYSTEM_ADMIN"]}

        # There is intentionally no API surface through which llm_output can enter
        # the authorization decision.
        self.assertNotIn("llm_output", PermissionService.is_allowed.__annotations__)
        self.assertTrue(llm_output["grant_access"])
        self.assertFalse(
            self.service.is_allowed(
                self.principal("EMPLOYEE"), ResourceAction.READ, resource
            )
        )

    def test_inactive_or_unauthenticated_principals_are_denied(self):
        resource = self.resource(ScopeType.COMPANY)
        for authenticated, active in ((False, True), (True, False)):
            principal = Principal(
                user_id=self.user_id,
                department_id=self.department_id,
                roles=frozenset({"SYSTEM_ADMIN"}),
                authenticated=authenticated,
                active=active,
            )
            self.assertFalse(
                self.service.is_allowed(principal, ResourceAction.READ, resource)
            )
