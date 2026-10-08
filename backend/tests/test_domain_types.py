import json
import unittest

from pydantic import BaseModel

from app.core.domain_types import (
    AccessLevel,
    ProcessingStatus,
    PublicationStatus,
    ResourceAction,
    ScopeType,
    SourceType,
)


class EnumEnvelope(BaseModel):
    scope: ScopeType
    access: AccessLevel
    action: ResourceAction


class DomainTypeTests(unittest.TestCase):
    def test_public_values_are_stable_strings(self):
        payload = EnumEnvelope(
            scope=ScopeType.PERSONAL_DRAFT,
            access=AccessLevel.CONFIDENTIAL,
            action=ResourceAction.APPROVE,
        )

        self.assertEqual(
            json.loads(payload.model_dump_json()),
            {
                "scope": "PERSONAL_DRAFT",
                "access": "CONFIDENTIAL",
                "action": "APPROVE",
            },
        )

    def test_all_declared_values_are_readable_and_stable(self):
        self.assertEqual(
            [item.value for item in ScopeType],
            ["COMPANY", "DEPARTMENT", "PROJECT", "PERSONAL_DRAFT"],
        )
        self.assertEqual(
            [item.value for item in AccessLevel],
            ["INTERNAL", "RESTRICTED", "CONFIDENTIAL"],
        )
        self.assertEqual(SourceType.DOCUMENT.value, "DOCUMENT")
        self.assertNotEqual(ProcessingStatus.READY.value, PublicationStatus.PUBLISHED.value)
