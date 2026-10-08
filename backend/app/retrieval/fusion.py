import re

from app.retrieval.types import FusedCandidate, RetrievalCandidate


def reciprocal_rank_fusion(fts: list[RetrievalCandidate], semantic: list[RetrievalCandidate], *, fts_weight: float, vector_weight: float, rrf_k: int) -> list[FusedCandidate]:
    if fts_weight <= 0 or vector_weight <= 0 or rrf_k <= 0:
        raise ValueError("RRF parameters must be positive")
    fused: dict = {}
    for channel, candidates, weight in (("FTS", fts, fts_weight), ("SEMANTIC", semantic, vector_weight)):
        for rank, candidate in enumerate(candidates, 1):
            item = fused.setdefault(candidate.chunk_id, FusedCandidate(candidate=candidate))
            item.fusion_score += weight / (rrf_k + rank)
            item.matched_by.add(channel)
            if candidate.fts_rank is not None:
                item.candidate = _merge(item.candidate, candidate)
            if candidate.semantic_similarity is not None:
                item.candidate = _merge(item.candidate, candidate)
    return sorted(fused.values(), key=lambda item: (-item.fusion_score, str(item.candidate.chunk_id)))


def _merge(left: RetrievalCandidate, right: RetrievalCandidate) -> RetrievalCandidate:
    values = {field: getattr(left, field) for field in left.__dataclass_fields__}
    values["fts_rank"] = right.fts_rank if right.fts_rank is not None else left.fts_rank
    values["semantic_similarity"] = right.semantic_similarity if right.semantic_similarity is not None else left.semantic_similarity
    return RetrievalCandidate(**values)


def deterministic_rerank(items: list[FusedCandidate], query: str, max_boost: float) -> list[FusedCandidate]:
    lowered = query.casefold()
    codes = set(re.findall(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)*\b", query))
    for item in items:
        reasons = []
        if lowered and lowered in item.candidate.source_title.casefold():
            reasons.append("SOURCE_TITLE_PHRASE")
        if item.candidate.section and lowered in item.candidate.section.casefold():
            reasons.append("SECTION_PHRASE")
        if any(code in item.candidate.content for code in codes):
            reasons.append("EXACT_CODE")
        if item.matched_by == {"FTS", "SEMANTIC"}:
            reasons.append("DUAL_CHANNEL")
        boost = min(max_boost, len(reasons) * (max_boost / 4 if max_boost else 0))
        item.fusion_score += boost
        item.rerank_reasons.extend(reasons)
    return sorted(items, key=lambda item: (-item.fusion_score, str(item.candidate.chunk_id)))
