from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    mrr: float
    evaluated_queries: int


def calculate_metrics(cases: list[dict], rankings: dict[str, list[str]]) -> EvaluationMetrics:
    eligible = [case for case in cases if case.get("acceptable_chunks")]
    if not eligible:
        return EvaluationMetrics(0.0, 0.0, 0.0, 0.0, 0)
    recalls = {1: 0, 3: 0, 5: 0}
    reciprocal_sum = 0.0
    for case in eligible:
        acceptable = set(case["acceptable_chunks"])
        ranked = rankings.get(case["id"], [])
        for k in recalls:
            recalls[k] += bool(acceptable.intersection(ranked[:k]))
        first = next((rank for rank, chunk in enumerate(ranked, 1) if chunk in acceptable), None)
        if first:
            reciprocal_sum += 1.0 / first
    count = len(eligible)
    return EvaluationMetrics(
        recall_at_1=recalls[1] / count,
        recall_at_3=recalls[3] / count,
        recall_at_5=recalls[5] / count,
        mrr=reciprocal_sum / count,
        evaluated_queries=count,
    )
