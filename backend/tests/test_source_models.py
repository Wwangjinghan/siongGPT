import unittest
from uuid import uuid4

from app.core.domain_types import ScopeType
from app.models.source import Source
from app.models.source_version import SourceVersion
from app.sources.errors import InvalidSourceError
from app.sources.services import SourceService


class SourceModelTests(unittest.TestCase):
    def test_scope_field_rules(self):
        department = uuid4()
        owner = uuid4()
        project = uuid4()
        valid = (
            (ScopeType.COMPANY, None, None, owner),
            (ScopeType.DEPARTMENT, department, None, None),
            (ScopeType.PERSONAL_DRAFT, None, None, owner),
            (ScopeType.PROJECT, None, project, None),
        )
        for args in valid:
            SourceService.validate_scope(*args)

    def test_invalid_scope_fields_are_rejected(self):
        invalid = (
            (ScopeType.DEPARTMENT, None, None, None),
            (ScopeType.PERSONAL_DRAFT, None, None, None),
            (ScopeType.COMPANY, None, uuid4(), None),
        )
        for args in invalid:
            with self.subTest(scope=args[0]), self.assertRaises(InvalidSourceError):
                SourceService.validate_scope(*args)

    def test_database_metadata_contains_immutable_and_current_constraints(self):
        unique_names = {constraint.name for constraint in SourceVersion.__table__.constraints}
        index_names = {index.name for index in SourceVersion.__table__.indexes}
        self.assertIn("uq_source_versions_hash", unique_names)
        self.assertIn("uq_source_versions_number", unique_names)
        self.assertIn("uq_source_versions_one_current", index_names)
        foreign_key = next(iter(SourceVersion.__table__.c.source_id.foreign_keys))
        self.assertIsNone(foreign_key.ondelete)

    def test_source_versions_are_not_delete_orphan_cascaded(self):
        relationship = Source.__mapper__.relationships["versions"]
        self.assertNotIn("delete", relationship.cascade)
