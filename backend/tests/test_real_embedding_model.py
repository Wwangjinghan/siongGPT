import os
import math
import unittest

from app.core.config import settings
from app.embeddings.local_e5 import LocalE5Provider


@unittest.skipUnless(
    os.path.isdir(settings.embedding_model_local_path),
    "pinned local E5 model is not present; automatic download is forbidden",
)
class RealEmbeddingModelTests(unittest.TestCase):
    def test_real_model_multilingual_smoke(self):
        provider = LocalE5Provider(
            model_name=settings.embedding_model_name,
            revision=settings.embedding_model_revision,
            local_path=settings.embedding_model_local_path,
            allow_download=False,
            device=settings.embedding_device,
            batch_size=3,
            max_sequence_length=settings.embedding_max_sequence_length,
        )
        passages = provider.embed_passages([
            "Employee expense claims require a purchase order and delivery order.",
            "员工报销需要提交采购订单、送货单和收据。",
            "The fictional cafeteria menu changes weekly.",
        ])
        cases = (
            ("expense claim documents", 0),
            ("报销需要什么文件", 0),
            ("What paperwork is required for employee reimbursement?", 1),
            ("员工报销要交哪些 documents?", 0),
        )
        for query, relevant_index in cases:
            vector = provider.embed_query(query)
            self.assertEqual(len(vector), 384)
            self.assertAlmostEqual(sum(value * value for value in vector), 1.0, places=5)
            related = sum(a * b for a, b in zip(vector, passages[relevant_index], strict=True))
            unrelated = sum(a * b for a, b in zip(vector, passages[2], strict=True))
            self.assertGreater(related, unrelated)

    def test_batch_single_stability_and_revision(self):
        provider = LocalE5Provider(
            model_name=settings.embedding_model_name,
            revision=settings.embedding_model_revision,
            local_path=settings.embedding_model_local_path,
            allow_download=False,
            device=settings.embedding_device,
            batch_size=3,
            max_sequence_length=settings.embedding_max_sequence_length,
        )
        texts = ["GST claim conditions", "项目编号 PRJ-001", "delivery order requirement"]
        batch = provider.embed_passages(texts)
        singles = [provider.embed_passages([text])[0] for text in texts]
        repeated = provider.embed_passages(texts)
        self.assertEqual(provider.profile().model_revision, settings.embedding_model_revision)
        for batch_vector, single_vector, repeated_vector in zip(batch, singles, repeated, strict=True):
            self.assertEqual(len(batch_vector), 384)
            self.assertTrue(math.isclose(sum(value * value for value in batch_vector), 1.0, abs_tol=1e-5))
            for left, right in zip(batch_vector, single_vector, strict=True):
                self.assertAlmostEqual(left, right, places=5)
            for left, right in zip(batch_vector, repeated_vector, strict=True):
                self.assertAlmostEqual(left, right, places=6)
